"""Service for pulling, classifying, and filing incoming faxes to patient charts in Elation.

Workflow:
1. Pull unfiled faxes from the Elation fax inbox
2. Extract patient-identifying information from fax metadata and OCR text
3. Match the fax to an existing patient in Elation
4. Classify the document type based on fax content
5. File the fax PDF to the matched patient's chart
6. Assign the document to the patient's provider for review/sign-off
7. Mark the fax as filed in the inbox
"""

import logging
import re
from datetime import datetime

from clients.elation_client import ElationClient

logger = logging.getLogger(__name__)

# ── Document Type Classification ───────────────────────────────────────
# Keywords mapped to Elation document types. Order matters — first match wins.
DOCUMENT_TYPE_RULES = [
    {
        "type": "Lab Report",
        "keywords": [
            "lab", "laboratory", "blood work", "bloodwork", "cbc", "cmp", "bmp",
            "lipid panel", "a1c", "hemoglobin", "hematology", "urinalysis",
            "pathology", "culture", "sensitivity", "specimen", "glucose",
            "cholesterol", "triglyceride", "creatinine", "bun", "thyroid",
            "tsh", "metabolic panel", "test result", "lab result",
        ],
    },
    {
        "type": "Imaging Report",
        "keywords": [
            "radiology", "x-ray", "xray", "ct scan", "mri", "ultrasound",
            "imaging", "mammogram", "mammography", "dexa", "bone density",
            "echocardiogram", "echo report", "nuclear", "pet scan", "fluoroscopy",
        ],
    },
    {
        "type": "Consultation Report",
        "keywords": [
            "consultation", "consult note", "specialist report", "evaluation",
            "assessment", "specialist opinion", "second opinion",
        ],
    },
    {
        "type": "Referral Letter",
        "keywords": [
            "referral", "refer to", "referring", "authorization for referral",
        ],
    },
    {
        "type": "Hospital Records",
        "keywords": [
            "discharge summary", "hospital", "admission", "inpatient",
            "emergency room", "er visit", "ed visit", "operative report",
            "surgery", "surgical", "procedure note", "post-op",
        ],
    },
    {
        "type": "Insurance/Authorization",
        "keywords": [
            "insurance", "authorization", "prior auth", "pre-authorization",
            "eob", "explanation of benefits", "coverage", "denial",
            "approval", "precertification",
        ],
    },
    {
        "type": "Prescription",
        "keywords": [
            "prescription", "rx", "medication", "refill", "pharmacy",
            "drug", "dosage", "dispense",
        ],
    },
    {
        "type": "Patient Correspondence",
        "keywords": [
            "patient letter", "correspondence", "request for records",
            "medical records", "release of information", "roi",
        ],
    },
]

DEFAULT_DOCUMENT_TYPE = "Other"

# ── Patient Name / DOB Extraction Patterns ─────────────────────────────
# Common patterns found on fax cover sheets, lab headers, and medical documents
PATIENT_NAME_PATTERNS = [
    # "Patient: Last, First" or "Patient Name: Last, First"
    r"[Pp]atient(?:\s*[Nn]ame)?\s*[:=]\s*([A-Za-z'-]+)\s*,\s*([A-Za-z'-]+)",
    # "Name: Last, First"
    r"[Nn]ame\s*[:=]\s*([A-Za-z'-]+)\s*,\s*([A-Za-z'-]+)",
    # "RE: Last, First" (common on consult/referral letters)
    r"[Rr][Ee]\s*[:=]\s*([A-Za-z'-]+)\s*,\s*([A-Za-z'-]+)",
    # "Patient: First Last"
    r"[Pp]atient(?:\s*[Nn]ame)?\s*[:=]\s*([A-Za-z'-]+)\s+([A-Za-z'-]+)",
    # "Attn.*Patient: First Last" or similar
    r"[Aa]ttn[:\s].*?([A-Za-z'-]+)\s*,\s*([A-Za-z'-]+)",
]

DOB_PATTERNS = [
    # "DOB: MM/DD/YYYY" or "DOB: MM-DD-YYYY"
    r"[Dd]\.?[Oo]\.?[Bb]\.?\s*[:=]\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})",
    # "Date of Birth: MM/DD/YYYY"
    r"[Dd]ate\s+of\s+[Bb]irth\s*[:=]\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})",
    # "Birth Date: MM/DD/YYYY"
    r"[Bb]irth\s*[Dd]ate\s*[:=]\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})",
]


class FaxFilingService:
    """Orchestrates pulling faxes from the inbox and filing them to patient charts."""

    def __init__(self, elation_client: ElationClient = None):
        self.elation = elation_client or ElationClient()

    def process_fax_inbox(self) -> dict:
        """Main entry point: pull unfiled faxes and file each one.

        Returns:
            Summary dict with counts of processed, filed, and failed faxes.
        """
        logger.info("=== Starting fax inbox processing ===")
        summary = {"total": 0, "filed": 0, "skipped": 0, "failed": 0, "details": []}

        try:
            faxes = self.elation.get_received_faxes(filing_status="new")
        except Exception:
            logger.exception("Failed to fetch received faxes from inbox")
            return summary

        summary["total"] = len(faxes)
        if not faxes:
            logger.info("No unfiled faxes in the inbox")
            return summary

        logger.info("Processing %d unfiled faxes", len(faxes))

        for fax in faxes:
            fax_id = fax.get("id")
            result = self._process_single_fax(fax)
            summary["details"].append({"fax_id": fax_id, **result})

            if result["status"] == "filed":
                summary["filed"] += 1
            elif result["status"] == "skipped":
                summary["skipped"] += 1
            else:
                summary["failed"] += 1

        logger.info(
            "Fax processing complete: %d total, %d filed, %d skipped, %d failed",
            summary["total"],
            summary["filed"],
            summary["skipped"],
            summary["failed"],
        )
        return summary

    def _process_single_fax(self, fax: dict) -> dict:
        """Process a single fax: identify patient, classify, and file.

        Returns:
            Dict with status ("filed", "skipped", "failed") and details.
        """
        fax_id = fax.get("id")
        logger.info("Processing fax %s from %s", fax_id, fax.get("from_number", "unknown"))

        # Step 1: Extract text content from fax for analysis
        text_content = fax.get("text", "") or fax.get("text_content", "") or ""

        # Step 2: Extract patient-identifying information
        patient_info = self._extract_patient_info(text_content, fax)
        if not patient_info.get("last_name"):
            logger.warning("Fax %s: Could not extract patient name, skipping", fax_id)
            return {
                "status": "skipped",
                "reason": "Could not identify patient from fax content",
            }

        # Step 3: Match to an Elation patient record
        patient = self._match_patient(patient_info)
        if not patient:
            logger.warning(
                "Fax %s: No matching patient found for %s %s (DOB: %s), skipping",
                fax_id,
                patient_info.get("first_name", ""),
                patient_info.get("last_name", ""),
                patient_info.get("dob", "N/A"),
            )
            return {
                "status": "skipped",
                "reason": (
                    f"No matching patient: {patient_info.get('first_name', '')} "
                    f"{patient_info.get('last_name', '')} "
                    f"(DOB: {patient_info.get('dob', 'N/A')})"
                ),
            }

        patient_id = patient["id"]
        patient_name = f"{patient.get('last_name', '')}, {patient.get('first_name', '')}"
        logger.info("Fax %s: Matched to patient %s (ID: %s)", fax_id, patient_name, patient_id)

        # Step 4: Determine the patient's assigned provider
        physician_id = patient.get("primary_physician") or patient.get("caregiver")
        if not physician_id:
            logger.warning(
                "Fax %s: Patient %s has no assigned provider, filing without provider assignment",
                fax_id,
                patient_name,
            )

        # Step 5: Classify the document type
        document_type = self._classify_document_type(text_content)
        logger.info("Fax %s: Classified as '%s'", fax_id, document_type)

        # Step 6: Download fax PDF and file to patient chart
        try:
            document_url = fax.get("document_url") or fax.get("file") or fax.get("url")
            if not document_url:
                logger.error("Fax %s: No document URL available", fax_id)
                return {"status": "failed", "reason": "No document URL in fax record"}

            pdf_content = self.elation.download_fax_document(document_url)

            from_number = fax.get("from_number", "unknown")
            received_date = fax.get("received_date", "") or fax.get("created_date", "")
            description = (
                f"Fax received from {from_number}. "
                f"Auto-classified as {document_type}. "
                f"Requires provider review and sign-off."
            )

            document_date = None
            if received_date:
                try:
                    dt = datetime.fromisoformat(received_date.replace("Z", "+00:00"))
                    document_date = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            filename = f"fax_{fax_id}_{patient_id}.pdf"

            doc_result = self.elation.create_document(
                patient_id=patient_id,
                document_type=document_type,
                file_content=pdf_content,
                filename=filename,
                physician_id=physician_id,
                description=description,
                document_date=document_date,
            )
            logger.info(
                "Fax %s: Document filed to patient %s chart (doc ID: %s)",
                fax_id,
                patient_name,
                doc_result.get("id"),
            )
        except Exception:
            logger.exception("Fax %s: Failed to file document to patient chart", fax_id)
            return {"status": "failed", "reason": "Error filing document to chart"}

        # Step 7: Mark fax as filed in the inbox
        try:
            self.elation.update_received_fax(fax_id, {
                "filing_status": "filed",
                "patient": patient_id,
            })
            logger.info("Fax %s: Marked as filed in inbox", fax_id)
        except Exception:
            logger.exception(
                "Fax %s: Document filed but failed to update fax status", fax_id
            )

        return {
            "status": "filed",
            "patient_id": patient_id,
            "patient_name": patient_name,
            "document_type": document_type,
            "physician_id": physician_id,
            "document_id": doc_result.get("id"),
        }

    # ── Patient Information Extraction ─────────────────────────────────

    def _extract_patient_info(self, text: str, fax: dict) -> dict:
        """Extract patient name and DOB from fax text content and metadata.

        Tries structured fax metadata fields first, then falls back to
        regex pattern matching against OCR text.

        Returns:
            Dict with keys: first_name, last_name, dob (may be partial).
        """
        info = {"first_name": None, "last_name": None, "dob": None}

        # Check fax metadata fields first (some fax systems include structured data)
        if fax.get("patient_first_name"):
            info["first_name"] = fax["patient_first_name"].strip()
        if fax.get("patient_last_name"):
            info["last_name"] = fax["patient_last_name"].strip()
        if fax.get("patient_dob"):
            info["dob"] = fax["patient_dob"]

        # If we already have a full name from metadata, try DOB from text
        if info["first_name"] and info["last_name"]:
            if not info["dob"]:
                info["dob"] = self._extract_dob(text)
            return info

        # Fall back to regex extraction from OCR text
        if text:
            name_info = self._extract_name(text)
            if name_info:
                info["first_name"] = info["first_name"] or name_info.get("first_name")
                info["last_name"] = info["last_name"] or name_info.get("last_name")

            if not info["dob"]:
                info["dob"] = self._extract_dob(text)

        return info

    def _extract_name(self, text: str) -> dict | None:
        """Extract patient name from text using regex patterns.

        Returns:
            Dict with first_name and last_name, or None if no match.
        """
        for pattern in PATIENT_NAME_PATTERNS:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    # Determine if format is "Last, First" or "First Last"
                    if "," in match.group(0):
                        return {"last_name": groups[0].strip(), "first_name": groups[1].strip()}
                    else:
                        return {"first_name": groups[0].strip(), "last_name": groups[1].strip()}
        return None

    def _extract_dob(self, text: str) -> str | None:
        """Extract date of birth from text.

        Returns:
            DOB as YYYY-MM-DD string, or None.
        """
        for pattern in DOB_PATTERNS:
            match = re.search(pattern, text)
            if match:
                month, day, year = match.groups()
                year = int(year)
                if year < 100:
                    year += 1900 if year > 30 else 2000
                try:
                    dob = datetime(year, int(month), int(day))
                    return dob.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    # ── Patient Matching ───────────────────────────────────────────────

    def _match_patient(self, patient_info: dict) -> dict | None:
        """Find a matching patient in Elation using extracted info.

        Matching strategy (in order of confidence):
        1. Last name + first name + DOB (exact match)
        2. Last name + DOB (handles first-name variations)
        3. Last name + first name (without DOB)

        Returns:
            The best-matching patient dict, or None.
        """
        first_name = patient_info.get("first_name", "")
        last_name = patient_info.get("last_name", "")
        dob = patient_info.get("dob")

        if not last_name:
            return None

        # Strategy 1: Full match with DOB
        if first_name and dob:
            results = self.elation.search_patients(
                first_name=first_name,
                last_name=last_name,
                dob=dob,
            )
            if len(results) == 1:
                return results[0]
            if len(results) > 1:
                logger.warning(
                    "Multiple patients matched for %s %s DOB %s, using first result",
                    first_name, last_name, dob,
                )
                return results[0]

        # Strategy 2: Last name + DOB (handles first-name nicknames/variations)
        if dob:
            results = self.elation.search_patients(last_name=last_name, dob=dob)
            if len(results) == 1:
                return results[0]
            if results and first_name:
                # Try fuzzy first-name matching within results
                best = self._best_first_name_match(results, first_name)
                if best:
                    return best

        # Strategy 3: Name only (less reliable, require exact single match)
        if first_name:
            results = self.elation.search_patients(
                first_name=first_name, last_name=last_name
            )
            if len(results) == 1:
                return results[0]

        return None

    def _best_first_name_match(self, patients: list[dict], first_name: str) -> dict | None:
        """Find the best first-name match from a list of patients.

        Handles common variations: "Rob" vs "Robert", "Mike" vs "Michael", etc.
        """
        first_lower = first_name.lower()
        for patient in patients:
            p_first = (patient.get("first_name") or "").lower()
            if p_first == first_lower:
                return patient
            if p_first.startswith(first_lower) or first_lower.startswith(p_first):
                return patient
        return None

    # ── Document Type Classification ───────────────────────────────────

    def _classify_document_type(self, text: str) -> str:
        """Classify the document type based on fax text content.

        Scans for keywords associated with each document type category.
        Returns the first matching type, or "Other" as the default.
        """
        if not text:
            return DEFAULT_DOCUMENT_TYPE

        text_lower = text.lower()

        for rule in DOCUMENT_TYPE_RULES:
            for keyword in rule["keywords"]:
                if keyword in text_lower:
                    return rule["type"]

        return DEFAULT_DOCUMENT_TYPE
