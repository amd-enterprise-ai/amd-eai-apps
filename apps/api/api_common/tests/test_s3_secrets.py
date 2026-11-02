# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from api_common.secrets import S3_REQUIRED_CREDENTIAL_KEYS, find_missing_s3_credential_types


def test_no_credentials_reports_both_missing():
    assert find_missing_s3_credential_types([]) == ["access key", "secret key"]


def test_only_access_key_reports_secret_key_missing():
    assert find_missing_s3_credential_types(["AWS_ACCESS_KEY_ID"]) == ["secret key"]


def test_only_secret_key_reports_access_key_missing():
    assert find_missing_s3_credential_types(["AWS_SECRET_ACCESS_KEY"]) == ["access key"]


def test_canonical_aws_keys_satisfy_requirements():
    assert find_missing_s3_credential_types(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]) == []


def test_minio_aliases_satisfy_requirements():
    assert find_missing_s3_credential_types(["minio-access-key", "minio-secret-key"]) == []


def test_storage_access_key_alias_satisfies_requirements():
    assert find_missing_s3_credential_types(["storage-access-key", "minio-secret-key"]) == []


def test_storage_secret_key_alias_satisfies_requirements():
    assert find_missing_s3_credential_types(["minio-access-key", "storage-secret-key"]) == []


def test_unrelated_keys_do_not_satisfy_requirements():
    assert find_missing_s3_credential_types(["token", "unrelated"]) == ["access key", "secret key"]


def test_required_key_logical_names_are_stable():
    assert set(S3_REQUIRED_CREDENTIAL_KEYS) == {"access key", "secret key"}
