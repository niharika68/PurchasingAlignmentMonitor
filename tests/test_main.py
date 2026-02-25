"""
Tests for the main module report generation functions.
Tests CSV and text report generation.
"""

import os
import pytest

# Import the report generation functions from main
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import generate_csv_report, generate_text_report


# Persistent test outputs directory
TEST_OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "test_outputs")


@pytest.fixture
def test_output_dir():
    """Fixture that provides a persistent test outputs directory."""
    os.makedirs(TEST_OUTPUTS_DIR, exist_ok=True)
    return TEST_OUTPUTS_DIR


@pytest.fixture
def sample_misaligned_hospitals():
    """Sample misaligned hospital data for testing."""
    return [
        {
            "hospital_id": "H001",
            "hospital_name": "City Medical Center",
            "quarterly_spend": 87500.0,
            "alignment_status": "MISALIGNED",
            "risk_level": "HIGH",
            "issues": "Off-contract purchase: DrugA; Off-contract purchase: DrugB",
        },
        {
            "hospital_id": "H002",
            "hospital_name": "Valley Health",
            "quarterly_spend": 62600.0,
            "alignment_status": "MISALIGNED",
            "risk_level": "MEDIUM",
            "issues": "Off-contract purchase: DrugX",
        },
    ]


@pytest.fixture
def sample_workflow_state(sample_misaligned_hospitals):
    """Sample workflow state for text report testing."""
    return {
        "hospital_analyses": [
            {
                "hospital_id": "H001",
                "hospital_name": "City Medical Center",
                "quarterly_spend": 87500.0,
                "alignment_status": "MISALIGNED",
                "risk_level": "HIGH",
                "issues": "Off-contract purchase: DrugA; Off-contract purchase: DrugB",
            },
            {
                "hospital_id": "H002",
                "hospital_name": "Valley Health",
                "quarterly_spend": 62600.0,
                "alignment_status": "MISALIGNED",
                "risk_level": "MEDIUM",
                "issues": "Off-contract purchase: DrugX",
            },
            {
                "hospital_id": "H003",
                "hospital_name": "Riverside Hospital",
                "quarterly_spend": 150000.0,
                "alignment_status": "ALIGNED",
                "risk_level": "LOW",
                "issues": "No issues detected",
            },
        ],
        "misaligned_hospitals": sample_misaligned_hospitals,
        "retrieval_errors": [],
    }


class TestGenerateCSVReport:
    """Tests for generate_csv_report function."""

    def test_csv_report_creates_file(self, sample_misaligned_hospitals, test_output_dir):
        """Test that CSV report file is created."""
        filepath = generate_csv_report(sample_misaligned_hospitals, test_output_dir)
        
        assert os.path.exists(filepath)
        assert filepath.endswith(".csv")

    def test_csv_report_contains_correct_data(self, sample_misaligned_hospitals, test_output_dir):
        """Test that CSV report contains expected data."""
        import pandas as pd
        
        filepath = generate_csv_report(sample_misaligned_hospitals, test_output_dir)
        df = pd.read_csv(filepath)
        
        assert len(df) == 2
        assert "H001" in df["hospital_id"].values
        assert "H002" in df["hospital_id"].values

    def test_csv_report_has_correct_columns(self, sample_misaligned_hospitals, test_output_dir):
        """Test that CSV report has expected columns."""
        import pandas as pd
        
        filepath = generate_csv_report(sample_misaligned_hospitals, test_output_dir)
        df = pd.read_csv(filepath)
        
        expected_columns = [
            "hospital_id",
            "hospital_name",
            "quarterly_spend",
            "alignment_status",
            "risk_level",
            "issues",
        ]
        
        for col in expected_columns:
            assert col in df.columns

    def test_csv_report_empty_list(self, test_output_dir):
        """Test that empty misaligned list creates CSV with headers only."""
        import pandas as pd
        
        filepath = generate_csv_report([], test_output_dir)
        df = pd.read_csv(filepath)
        
        assert len(df) == 0
        assert "hospital_id" in df.columns

    def test_csv_filename_format(self, sample_misaligned_hospitals, test_output_dir):
        """Test that CSV filename follows expected format."""
        filepath = generate_csv_report(sample_misaligned_hospitals, test_output_dir)
        filename = os.path.basename(filepath)
        
        assert filename.startswith("misaligned_hospitals_q")
        assert filename.endswith(".csv")


class TestGenerateTextReport:
    """Tests for generate_text_report function."""

    def test_text_report_contains_header(self, sample_workflow_state):
        """Test that text report contains header."""
        report = generate_text_report(sample_workflow_state)
        
        assert "PURCHASING ALIGNMENT MONITOR" in report
        assert "ANALYSIS REPORT" in report

    def test_text_report_contains_summary(self, sample_workflow_state):
        """Test that text report contains summary section."""
        report = generate_text_report(sample_workflow_state)
        
        assert "SUMMARY" in report
        assert "Total Hospitals Analyzed: 3" in report
        assert "Misaligned Hospitals: 2" in report

    def test_text_report_lists_misaligned_hospitals(self, sample_workflow_state):
        """Test that text report lists misaligned hospitals."""
        report = generate_text_report(sample_workflow_state)
        
        assert "City Medical Center" in report
        assert "Valley Health" in report
        assert "H001" in report
        assert "H002" in report

    def test_text_report_shows_risk_levels(self, sample_workflow_state):
        """Test that text report shows risk levels."""
        report = generate_text_report(sample_workflow_state)
        
        assert "HIGH" in report
        assert "MEDIUM" in report

    def test_text_report_shows_issues(self, sample_workflow_state):
        """Test that text report shows issues."""
        report = generate_text_report(sample_workflow_state)
        
        assert "Off-contract purchase" in report

    def test_text_report_empty_misaligned(self):
        """Test text report when no hospitals are misaligned."""
        state = {
            "hospital_analyses": [
                {
                    "hospital_id": "H001",
                    "hospital_name": "Good Hospital",
                    "quarterly_spend": 100000.0,
                    "alignment_status": "ALIGNED",
                    "risk_level": "LOW",
                    "issues": "No issues detected",
                }
            ],
            "misaligned_hospitals": [],
            "retrieval_errors": [],
        }
        
        report = generate_text_report(state)
        
        assert "All hospitals are aligned" in report

    def test_text_report_with_retrieval_errors(self):
        """Test text report includes retrieval errors."""
        state = {
            "hospital_analyses": [],
            "misaligned_hospitals": [],
            "retrieval_errors": ["Failed to connect to S3", "Contract not found"],
        }
        
        report = generate_text_report(state)
        
        assert "RETRIEVAL ISSUES" in report
        assert "Failed to connect to S3" in report

    def test_text_report_saves_to_file(self, sample_workflow_state, test_output_dir):
        """Test that text report can be saved to file."""
        report = generate_text_report(sample_workflow_state)
        
        filepath = os.path.join(test_output_dir, "test_analysis_report.txt")
        with open(filepath, "w") as f:
            f.write(report)
        
        assert os.path.exists(filepath)
        
        with open(filepath, "r") as f:
            saved_content = f.read()
        
        assert saved_content == report
        assert "PURCHASING ALIGNMENT MONITOR" in saved_content
