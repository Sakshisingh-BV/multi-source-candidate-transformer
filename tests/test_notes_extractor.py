"""Tests for src/extractors/notes_extractor.py"""

import unittest
from src.extractors.notes_extractor import (
    NotesExtractor,
    _extract_name, _extract_emails, _extract_phones,
    _extract_urls, _extract_skills, _extract_experience,
    _extract_education, _extract_location, _split_into_blocks,
)


SAKSHI_BLOCK = """Candidate: Sakshi Singh
Email: sakshi.s@gmail.com
Phone: +91 98765 43210

Spoke to Sakshi on 15 June 2025. Senior Software Developer at TechNova.

Skills mentioned in conversation:
- Python, JavaScript, React, SQL, REST APIs, Docker

LinkedIn: https://linkedin.com/in/sakshisingh
GitHub: https://github.com/sakshisingh

Experience:
- TechNova Solutions | Senior Software Developer | 2022-06 to present
- WebStart Labs | Junior Developer | 2021-01 to 2022-05

Education:
- B.Tech Computer Science | Rajasthan Technical University | 2021

Location: Jaipur, Rajasthan, India

Notes: Strong communication skills."""

RAHUL_BLOCK = """Candidate: Rahul Sharma
Email: rahul.sharma@email.com
Phone: +91-91234-56789

Skills: Python, SQL, Tableau, Excel, Power BI, Machine Learning

LinkedIn: https://linkedin.com/in/rahulsharma-data
Portfolio: https://rahulsharma.dev

Experience:
- DataSoft Inc | Senior Data Analyst | 2021-03 to present
- FinMetrics | Analyst Intern | 2020-06 to 2020-12

Education:
- M.Sc Statistics | Delhi University | 2020

Location: New Delhi, India"""

MULTI_BLOCK_FILE = f"--- Candidate Notes ---\n\n{SAKSHI_BLOCK}\n\n---\n\n{RAHUL_BLOCK}"


class TestBlockSplitter(unittest.TestCase):
    def test_splits_two_candidate_blocks(self):
        blocks = _split_into_blocks(MULTI_BLOCK_FILE)
        self.assertEqual(len(blocks), 2)

    def test_skips_header_block_without_candidate(self):
        blocks = _split_into_blocks(MULTI_BLOCK_FILE)
        for block in blocks:
            self.assertIn("Candidate:", block)

    def test_empty_file_returns_no_blocks(self):
        self.assertEqual(_split_into_blocks(""), [])


class TestExtractName(unittest.TestCase):
    def test_extracts_sakshi(self):
        self.assertEqual(_extract_name(SAKSHI_BLOCK), "Sakshi Singh")

    def test_extracts_rahul(self):
        self.assertEqual(_extract_name(RAHUL_BLOCK), "Rahul Sharma")

    def test_returns_none_when_missing(self):
        self.assertIsNone(_extract_name("No name here"))


class TestExtractEmails(unittest.TestCase):
    def test_extracts_single_email(self):
        self.assertIn("sakshi.s@gmail.com", _extract_emails(SAKSHI_BLOCK))

    def test_no_duplicates(self):
        block = "Email: same@test.com\nAlso: same@test.com"
        self.assertEqual(len(_extract_emails(block)), 1)

    def test_returns_empty_when_none(self):
        self.assertEqual(_extract_emails("No email here"), [])


class TestExtractPhones(unittest.TestCase):
    def test_extracts_indian_phone(self):
        phones = _extract_phones(SAKSHI_BLOCK)
        self.assertTrue(len(phones) >= 1)
        # Should contain digits from +91 98765 43210
        combined = "".join(phones)
        self.assertIn("9876543210", combined.replace(" ", "").replace("-", ""))

    def test_returns_empty_for_short_numbers(self):
        self.assertEqual(_extract_phones("Call 12345"), [])


class TestExtractUrls(unittest.TestCase):
    def test_linkedin_classified(self):
        links = _extract_urls(SAKSHI_BLOCK)
        self.assertEqual(links["linkedin"], "https://linkedin.com/in/sakshisingh")

    def test_github_classified(self):
        links = _extract_urls(SAKSHI_BLOCK)
        self.assertEqual(links["github"], "https://github.com/sakshisingh")

    def test_portfolio_classified(self):
        links = _extract_urls(RAHUL_BLOCK)
        self.assertEqual(links["portfolio"], "https://rahulsharma.dev")

    def test_no_urls_returns_empty_dict(self):
        links = _extract_urls("No links here")
        self.assertIsNone(links["linkedin"])
        self.assertIsNone(links["github"])


class TestExtractSkills(unittest.TestCase):
    def test_extracts_python(self):
        skills = _extract_skills(SAKSHI_BLOCK)
        self.assertIn("Python", skills)

    def test_extracts_multiple_skills(self):
        skills = _extract_skills(SAKSHI_BLOCK)
        self.assertGreater(len(skills), 3)

    def test_rahul_skills_extracted(self):
        skills = _extract_skills(RAHUL_BLOCK)
        self.assertIn("Machine Learning", skills)

    def test_returns_list(self):
        self.assertIsInstance(_extract_skills(SAKSHI_BLOCK), list)


class TestExtractExperience(unittest.TestCase):
    def test_extracts_two_entries_for_sakshi(self):
        exp = _extract_experience(SAKSHI_BLOCK)
        self.assertEqual(len(exp), 2)

    def test_company_parsed(self):
        exp = _extract_experience(SAKSHI_BLOCK)
        companies = [e["company"] for e in exp]
        self.assertIn("TechNova Solutions", companies)

    def test_title_parsed(self):
        exp = _extract_experience(SAKSHI_BLOCK)
        titles = [e["title"] for e in exp]
        self.assertIn("Senior Software Developer", titles)

    def test_start_date_parsed(self):
        exp = _extract_experience(SAKSHI_BLOCK)
        technova = next(e for e in exp if e["company"] == "TechNova Solutions")
        self.assertEqual(technova["start"], "2022-06")

    def test_present_end_date_is_none(self):
        exp = _extract_experience(SAKSHI_BLOCK)
        technova = next(e for e in exp if e["company"] == "TechNova Solutions")
        self.assertIsNone(technova["end"])

    def test_closed_date_range_parsed(self):
        exp = _extract_experience(SAKSHI_BLOCK)
        webstart = next(e for e in exp if e["company"] == "WebStart Labs")
        self.assertEqual(webstart["end"], "2022-05")

    def test_returns_empty_when_no_section(self):
        self.assertEqual(_extract_experience("No experience section"), [])


class TestExtractEducation(unittest.TestCase):
    def test_extracts_one_entry(self):
        edu = _extract_education(SAKSHI_BLOCK)
        self.assertEqual(len(edu), 1)

    def test_institution_parsed(self):
        edu = _extract_education(SAKSHI_BLOCK)
        self.assertEqual(edu[0]["institution"], "Rajasthan Technical University")

    def test_degree_parsed(self):
        edu = _extract_education(SAKSHI_BLOCK)
        self.assertEqual(edu[0]["degree"], "B.Tech")

    def test_field_parsed(self):
        edu = _extract_education(SAKSHI_BLOCK)
        self.assertEqual(edu[0]["field"], "Computer Science")

    def test_end_year_parsed(self):
        edu = _extract_education(SAKSHI_BLOCK)
        self.assertEqual(edu[0]["end_year"], 2021)


class TestExtractLocation(unittest.TestCase):
    def test_extracts_location(self):
        loc = _extract_location(SAKSHI_BLOCK)
        self.assertEqual(loc, "Jaipur, Rajasthan, India")

    def test_returns_none_when_missing(self):
        self.assertIsNone(_extract_location("No location"))


class TestNotesExtractorFull(unittest.TestCase):
    def test_extracts_two_records_from_file(self):
        records = NotesExtractor().extract("data/recruiter_notes.txt")
        self.assertEqual(len(records), 2)

    def test_all_records_have_source_id(self):
        for rec in NotesExtractor().extract("data/recruiter_notes.txt"):
            self.assertEqual(rec.source_id, "recruiter_notes")

    def test_missing_file_returns_error_record_not_crash(self):
        records = NotesExtractor().extract("data/nonexistent.txt")
        self.assertEqual(len(records), 1)
        self.assertTrue(len(records[0].errors) > 0)

    def test_first_record_has_name(self):
        records = NotesExtractor().extract("data/recruiter_notes.txt")
        self.assertEqual(records[0].data.get("full_name"), "Sakshi Singh")

    def test_records_have_experience(self):
        records = NotesExtractor().extract("data/recruiter_notes.txt")
        self.assertTrue(len(records[0].data.get("experience", [])) > 0)

    def test_records_have_education(self):
        records = NotesExtractor().extract("data/recruiter_notes.txt")
        self.assertTrue(len(records[0].data.get("education", [])) > 0)


if __name__ == "__main__":
    unittest.main()
