# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import uuid
from io import BytesIO

import pytest
import yaml
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.charts.schemas import (
    ChartCreate,
    ChartFile,
    ChartResponse,
    ChartSignature,
    ChartUpdate,
    _parse_chart_files,
    _parse_signature_file,
)
from app.workloads.enums import WorkloadType


def test_chart_file_schema():
    """Test ChartFile schema validation."""
    # Valid data
    valid_data = {"path": "file.txt", "content": "test content"}
    file = ChartFile(**valid_data)
    assert file.path == "file.txt"
    assert file.content == "test content"

    # Invalid data (missing field)
    with pytest.raises(ValidationError):
        ChartFile(path="file.txt")


def test_chart_create_schema():
    """Test ChartCreate schema validation."""
    # Valid data with UploadFile objects
    signature_file = UploadFile(filename="signature.yaml", file=BytesIO(b"key: value"))
    chart_files = [UploadFile(filename="f.txt", file=BytesIO(b"c"))]

    chart_create = ChartCreate(
        name="Test Chart",
        type=WorkloadType.FINE_TUNING,
        signature=signature_file,
        files=chart_files,
        tags=["test", "chart"],
    )
    assert chart_create.name == "Test Chart"
    assert chart_create.type == WorkloadType.FINE_TUNING
    assert chart_create.signature.filename == "signature.yaml"
    assert len(chart_create.files) == 1
    assert chart_create.files[0].filename == "f.txt"
    assert chart_create.tags == ["test", "chart"]

    # Invalid data (name too short)
    with pytest.raises(ValidationError):
        ChartCreate(name="Te", type=WorkloadType.FINE_TUNING, signature=signature_file, files=chart_files)

    # Missing required field (signature)
    with pytest.raises(ValidationError):
        ChartCreate(name="Test Chart", type=WorkloadType.FINE_TUNING, files=chart_files)


def test_chart_file_response_schema():
    """Test ChartFile schema validation."""
    valid_data = {"path": "response.txt", "content": "response content"}
    response = ChartFile(**valid_data)
    assert response.path == "response.txt"
    assert response.content == "response content"

    # Invalid data (missing content)
    with pytest.raises(ValidationError):
        ChartFile(path="response.txt")


def test_chart_full_response_schema():
    """Test ChartResponse schema including the field validator."""
    # Valid data (BaseEntityPublic fields + files)
    entity_data = {
        "id": uuid.uuid4(),
        "created_at": "2023-01-01T10:00:00Z",
        "updated_at": "2023-01-01T11:00:00Z",
        "created_by": "user1",
        "updated_by": "user2",
    }
    file_data = [{"path": "r.txt", "content": "rc"}]
    valid_data = {
        **entity_data,
        "name": "test-response-chart",
        "slug": "test-response-chart-slug",
        "display_name": "Test Response Chart Display",
        "type": WorkloadType.FINE_TUNING,
        "files": file_data,
        "signature": {},
        "usage_scope": "user",
    }

    response = ChartResponse(**valid_data)
    assert response.id == entity_data["id"]
    assert len(response.files) == 1
    assert isinstance(response.files[0], ChartFile)
    assert response.files[0].path == "r.txt"
    assert isinstance(response.signature, ChartSignature)
    assert response.signature.image is None


def test_chart_signature_typed_image_and_extra_keys():
    """ChartSignature types `image` and tolerates arbitrary extra YAML keys."""
    signature = ChartSignature(image="registry.example.com/foo:latest", replicas=1, model_name="test-model")
    assert signature.image == "registry.example.com/foo:latest"
    dumped = signature.model_dump(by_alias=True)
    # Extra free-form signature keys survive round-tripping (extra="allow").
    assert dumped["replicas"] == 1
    assert dumped["model_name"] == "test-model"


def test_chart_signature_image_optional():
    """A signature without `image` (e.g. workspace charts) is valid."""
    assert ChartSignature().image is None
    assert ChartSignature(key="value").image is None


@pytest.mark.asyncio
async def test_parse_signature_file_valid_yaml() -> None:
    """Test parsing valid YAML signature file."""
    yaml_content = yaml.dump({"param": "value", "foo": "bar"})
    upload_file = UploadFile(filename="values.yaml", file=BytesIO(yaml_content.encode()))

    result = await _parse_signature_file(upload_file)

    assert isinstance(result, dict)
    assert result["param"] == "value"
    assert result["foo"] == "bar"


@pytest.mark.asyncio
async def test_parse_signature_file_empty_file() -> None:
    """Test parsing empty signature file."""
    upload_file = UploadFile(filename="values.yaml", file=BytesIO(b""))

    result = await _parse_signature_file(upload_file)

    # An empty document (yaml.safe_load -> None) is coerced to {} so the stored
    # signature is always an object and ChartResponse.signature validates.
    assert result == {}


@pytest.mark.asyncio
async def test_parse_signature_file_comments_only() -> None:
    """A comments-only document also parses to None and is coerced to {}."""
    upload_file = UploadFile(filename="values.yaml", file=BytesIO(b"# just a comment\n"))

    result = await _parse_signature_file(upload_file)

    assert result == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        b"- a\n- b\n",  # list root
        b"[]\n",  # empty list (falsy, but still not a mapping)
        b"just a string\n",  # scalar string root
        b"42\n",  # scalar int root
        b"false\n",  # scalar bool root
    ],
)
async def test_parse_signature_file_non_mapping_root_rejected(content: bytes) -> None:
    """Non-mapping YAML roots are rejected at parse time rather than persisted as a
    shape that would later 500 during ChartResponse.signature validation."""
    upload_file = UploadFile(filename="values.yaml", file=BytesIO(content))

    with pytest.raises(ValueError, match="must contain a YAML mapping"):
        await _parse_signature_file(upload_file)


@pytest.mark.asyncio
async def test_parse_signature_file_invalid_yaml() -> None:
    """Test parsing invalid YAML signature file."""
    upload_file = UploadFile(filename="bad.yaml", file=BytesIO(b"bad: ["))

    with pytest.raises(ValueError, match="Invalid YAML in signature file"):
        await _parse_signature_file(upload_file)


@pytest.mark.asyncio
async def test_parse_chart_files_valid_files() -> None:
    """Test parsing valid chart files."""
    files = [
        UploadFile(filename="file1.yaml", file=BytesIO(b"content 1")),
        UploadFile(filename="file2.yaml", file=BytesIO(b"content 2")),
    ]

    result = await _parse_chart_files(files)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["path"] == "file1.yaml"
    assert result[0]["content"] == "content 1"
    assert result[1]["path"] == "file2.yaml"
    assert result[1]["content"] == "content 2"


def make_chart_kwargs():
    return dict(name="Test Chart", type=WorkloadType.FINE_TUNING, signature="sig.yaml", files=["f.yaml"])


def test_chartcreate_tags_list():
    chart = ChartCreate(**make_chart_kwargs(), tags=["tag1", "tag2"])
    assert chart.tags == ["tag1", "tag2"]


def test_chartcreate_tags_json_string():
    chart = ChartCreate(**make_chart_kwargs(), tags='["tag1", "tag2"]')
    assert chart.tags == ["tag1", "tag2"]


def test_chartcreate_tags_json_string_not_list():
    with pytest.raises(ValidationError):
        ChartCreate(**make_chart_kwargs(), tags='"notalist"')


def test_chartcreate_tags_invalid_json():
    with pytest.raises(ValidationError):
        ChartCreate(**make_chart_kwargs(), tags="[invalid json]")


def test_chartupdate_tags_list():
    chart = ChartUpdate(tags=["tag1", "tag2"])
    assert chart.tags == ["tag1", "tag2"]


def test_chartupdate_tags_json_string():
    chart = ChartUpdate(tags='["tag1", "tag2"]')
    assert chart.tags == ["tag1", "tag2"]


def test_chartupdate_tags_json_string_not_list():
    with pytest.raises(ValidationError):
        ChartUpdate(tags='"notalist"')


def test_chartupdate_tags_invalid_json():
    with pytest.raises(ValidationError):
        ChartUpdate(tags="[invalid json]")
