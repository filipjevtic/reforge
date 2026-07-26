import re
from pathlib import Path

S3 = Path("/workspace/s3.tf")


def test_bucket_defined():
    text = S3.read_text()
    assert re.search(r'resource\s+"aws_s3_bucket"\s+"app_data"', text)


def test_bucket_uses_local_name():
    assert "local.bucket_name" in S3.read_text()
