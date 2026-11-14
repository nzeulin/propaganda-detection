import base64
import json
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError, AsyncOpenAI
from PIL import Image, PngImagePlugin

from app.content.image_analysis import ImageEvidenceReview, ImageObservation, apply_image_review, assess_image
from app.main import app
from app.providers.image_vision import ImageAnalyzer

URL = "/api/v1/images/analyze"
CAPTION = "In this archive lesson, the poster is shown as a recruiting example."


def image_bytes(size=(100, 80), format="PNG", **options):
    output = BytesIO()
    with Image.new("RGB", size, "black") as image:
        image.save(output, format=format, **options)
    return output.getvalue()


def observation(**changes):
    report = {
        "description": "A poster shows an oversized dark figure above the command ENLIST.",
        "image_text": "ENLIST",
        "text_status": "readable",
        "caption_assessment": {"stance": "neutrally_reported", "excerpt": "shown as a recruiting example"},
        "findings": [
            {
                "technique": "appeal_to_fear",
                "explanation": "The looming figure makes the demand to enlist feel urgent.",
                "evidence": [
                    {"source": "visual", "excerpt": "An oversized dark figure dominates the upper half."},
                    {"source": "image_text", "excerpt": "ENLIST"},
                ],
            }
        ],
        "context_needed": None,
    }
    return report | changes


def check(index=0, decision="supported", **changes):
    return {
        "candidate_index": index,
        "decision": decision,
        "alternative_explanation": "The figure could be a historic illustration.",
        "reason": "The figure is positioned to reinforce the direct appeal to enlist.",
        "visible_quotes": ["ENLIST"],
    } | changes


def review(*findings, stance="neutrally_reported", excerpt="shown as a recruiting example"):
    return {"findings": list(findings), "caption_assessment": {"stance": stance, "excerpt": excerpt}}


@pytest.fixture
def http(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    monkeypatch.setenv("IMAGE_ANALYSIS_ENABLED", "false")
    with TestClient(app) as client:
        yield client


def mock_analyzer(transport):
    client = AsyncOpenAI(
        api_key="mock-key",
        base_url="https://example.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    )
    return ImageAnalyzer(client, "test-vision")


def reply(report=None, status="completed"):
    content = (
        {"type": "output_text", "annotations": [], "text": json.dumps(report)}
        if report is not None
        else {"type": "refusal", "refusal": "Provider refused"}
    )
    return httpx.Response(
        200,
        json={
            "id": "resp_test",
            "object": "response",
            "created_at": 0,
            "status": status,
            "model": "test-vision-pinned",
            "output": [
                {
                    "id": "msg_test",
                    "role": "assistant",
                    "status": "completed",
                    "type": "message",
                    "content": [content],
                }
            ],
        },
    )


def upload(http, data=None, caption=CAPTION):
    return http.post(
        URL,
        files={"image": ("source.png", image_bytes() if data is None else data, "image/png")},
        data={"caption": caption},
    )


def test_disabled_reports_configuration_and_keeps_existing_routes(http):
    assert upload(http).status_code == 503
    assert http.get("/health").json()["live_configured"] is False
    assert http.post("/analyze", json={"example_id": "public-notice"}).status_code == 200
    contract = http.get("/openapi.json").json()["paths"][URL]["post"]
    assert "multipart/form-data" in contract["requestBody"]["content"]


def test_sdk_request_uses_actual_pixels_caption_and_no_metadata(http):
    seen = []

    def provider(request):
        assert request.url.path == "/v1/responses"
        body = json.loads(request.content)
        assert body["model"] == "test-vision"
        assert body["store"] is False
        assert "tools" not in body
        assert body["text"]["format"]["strict"] is True
        content = body["input"][0]["content"]
        payload = json.loads(content[0]["text"])
        assert payload["caption"] == CAPTION
        data_url = content[1]["image_url"]
        assert data_url.startswith("data:image/png;base64,")
        with Image.open(BytesIO(base64.b64decode(data_url.split(",")[1]))) as sent:
            assert sent.format == "PNG"
            assert sent.size == (2048, 68)
            assert sent.getpixel((0, 0)) == (0, 0, 0)
            assert "author" not in sent.info
        seen.append(body["instructions"])
        if len(seen) == 1:
            assert payload == {"caption": CAPTION}
            return reply(observation())
        assert payload["candidates"][0]["candidate_index"] == 0
        assert payload["candidates"][0]["technique"] == "appeal_to_fear"
        return reply(review(check()))

    http.app.state.image_analyzer = mock_analyzer(provider)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("author", "private metadata")
    result = upload(http, image_bytes((2400, 80), pnginfo=metadata))
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["status"] == "signals_found"
    assert report["model"] == "test-vision-pinned"
    assert report["image_text"] == "ENLIST"
    assert report["caption_assessment"]["stance"] == "neutrally_reported"
    assert report["findings"][0]["technique"] == "appeal_to_fear"
    assert len(seen) == 2
    assert seen[0] != seen[1]


def test_rules_do_not_guarantee_author_endorsement_or_keep_unanchored_text():
    raw = observation(
        image_text="JOIN OUR CLUB",
        caption_assessment={"stance": "endorsed", "excerpt": "I support this"},
    )
    bad = assess_image(ImageObservation.model_validate(raw), CAPTION, "test")
    assert bad.status == "needs_context"
    assert bad.caption_assessment.stance == "unclear"
    assert not bad.findings

    # The image's technique can remain when the caption explicitly rejects it.
    caption = "I reject this poster's appeal."
    rejected = observation(caption_assessment={"stance": "rejected", "excerpt": "I reject this poster"})
    report = assess_image(ImageObservation.model_validate(rejected), caption, "test")
    assert report.caption_assessment.stance == "rejected"
    assert report.findings


def test_unreadable_image_and_benign_image_are_separate_outcomes():
    unreadable = ImageObservation.model_validate(
        observation(image_text="invented", text_status="unreadable", findings=[])
    )
    report = assess_image(unreadable, "", "test")
    assert report.image_text == ""
    assert report.status == "needs_context"
    assert report.caption_assessment.stance == "not_provided"
    benign = unreadable.model_copy(update={"text_status": "no_visible_text"})
    assert assess_image(benign, "", "test").status == "no_clear_signals"
    assert assess_image(benign, "Maybe that's what they want.", "test").status == "needs_context"


@pytest.mark.parametrize("format", ["JPEG", "WEBP"])
def test_supported_formats_are_decoded_instead_of_trusting_the_extension(http, format):
    http.app.state.image_analyzer = mock_analyzer(lambda _: reply(observation(findings=[])))
    assert upload(http, image_bytes(format=format)).status_code == 200


def test_caption_is_optional(http):
    http.app.state.image_analyzer = mock_analyzer(lambda _: reply(observation(findings=[])))
    response = http.post(URL, files={"image": ("source.png", image_bytes(), "image/png")})
    assert response.status_code == 200
    assert response.json()["caption_assessment"] == {"stance": "not_provided", "excerpt": None}


@pytest.mark.parametrize(
    ("second_pass", "expected_status", "expected_caption"),
    [
        (review(check(decision="unsupported")), "no_clear_signals", "neutrally_reported"),
        (review(check(decision="needs_context")), "needs_context", "neutrally_reported"),
        (review(check(visible_quotes=[])), "needs_context", "neutrally_reported"),
        (review(check(), stance="endorsed", excerpt="In this archive lesson"), "signals_found", "unclear"),
        (review(check(), excerpt="invented quote"), "signals_found", "unclear"),
        (review(check(), check()), "needs_context", "unclear"),
        (review(check(index=1)), "needs_context", "unclear"),
        (review(), "needs_context", "neutrally_reported"),
        (None, "needs_context", "unclear"),
    ],
)
def test_only_reviewed_signals_survive_without_upgrading_caption(
    second_pass, expected_status, expected_caption
):
    report = assess_image(ImageObservation.model_validate(observation()), CAPTION, "test")
    parsed = ImageEvidenceReview.model_validate(second_pass) if second_pass else None
    checked = apply_image_review(report, parsed, CAPTION)
    assert checked.status == expected_status
    assert bool(checked.findings) == (expected_status == "signals_found")
    assert checked.caption_assessment.stance == expected_caption


def test_reports_can_contain_supported_and_uncertain_findings():
    raw = observation()
    raw["findings"].append(
        {
            "technique": "appeal_to_authority",
            "explanation": "A possible official seal appears at the bottom of the poster.",
            "evidence": [{"source": "visual", "excerpt": "A blurred circular mark in the lower right."}],
        }
    )
    report = assess_image(ImageObservation.model_validate(raw), CAPTION, "test")
    checked = apply_image_review(
        report,
        ImageEvidenceReview.model_validate(
            review(
                check(),
                check(
                    index=1,
                    decision="needs_context",
                    reason="Read the mark in a higher-resolution image.",
                    visible_quotes=[],
                ),
            )
        ),
        CAPTION,
    )
    assert [finding.technique for finding in checked.findings] == ["appeal_to_fear"]
    assert checked.status == "signals_found"
    assert checked.context_needed == "Read the mark in a higher-resolution image."


def test_no_evidence_or_stance_skips_second_provider_call(http):
    seen = []

    def provider(request):
        seen.append(request)
        return reply(observation(findings=[]))

    http.app.state.image_analyzer = mock_analyzer(provider)
    response = upload(http, caption="")
    assert response.json()["status"] == "no_clear_signals"
    assert len(seen) == 1


@pytest.mark.parametrize("failure", ["timeout", "invalid_schema", "refusal"])
def test_second_provider_failure_withholds_unreviewed_findings(http, failure):
    def provider(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        if "candidates" not in payload:
            return reply(observation())
        if failure == "timeout":
            raise APITimeoutError(request=request)
        if failure == "invalid_schema":
            return reply(review(check(decision="certain")))
        return reply()

    http.app.state.image_analyzer = mock_analyzer(provider)
    response = upload(http)
    assert response.status_code == 200
    assert response.json()["status"] == "needs_context"
    assert response.json()["findings"] == []


def test_explicit_caption_stance_gets_review_even_without_visual_findings(http):
    def provider(request):
        payload = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        if payload.get("candidates") == []:
            return reply(review(stance="unclear", excerpt=None))
        return reply(observation(findings=[]))

    http.app.state.image_analyzer = mock_analyzer(provider)
    result = upload(http).json()
    assert result["caption_assessment"]["stance"] == "unclear"
    assert result["status"] == "needs_context"


def test_rejects_bad_or_oversized_uploads_before_provider_call(http):
    def unexpected(request):
        pytest.fail("Invalid input reached the provider")

    http.app.state.image_analyzer = mock_analyzer(unexpected)
    assert upload(http, b"").status_code == 422
    assert upload(http, b'<svg xmlns="http://www.w3.org/2000/svg"/>').status_code == 415
    assert upload(http, image_bytes()[:30]).status_code == 415
    assert upload(http, b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert upload(http, b"x" * (6 * 1024 * 1024)).status_code == 413
    assert upload(http, image_bytes((4100, 4000))).status_code == 413
    assert upload(http, caption="x" * 2001).status_code == 422
    assert http.post(URL, json={"url": "http://example.test/photo.png"}).status_code == 415


def test_animated_png_is_rejected(http):
    def unexpected(request):
        pytest.fail("Animated input reached the provider")

    http.app.state.image_analyzer = mock_analyzer(unexpected)
    with Image.new("RGB", (100, 80), "red") as frame:
        animated = image_bytes(save_all=True, append_images=[frame])
    assert upload(http, animated).status_code == 415


@pytest.mark.parametrize("failure", ["refused", "incomplete", "malformed", "rate_limit", "timeout"])
def test_provider_failures_return_errors_without_inventing_findings(http, failure):
    def provider(request):
        if failure == "refused":
            return reply()
        if failure == "incomplete":
            return reply(observation(), status="incomplete")
        if failure == "malformed":
            return reply(observation(findings=[{"technique": "invented"}]))
        if failure == "timeout":
            raise APITimeoutError(request=request)
        return httpx.Response(429, json={"error": {"message": "Provider rate limit"}})

    http.app.state.image_analyzer = mock_analyzer(provider)
    result = upload(http)
    assert result.status_code == (504 if failure == "timeout" else 502), result.text
    assert set(result.json()) == {"detail"}
