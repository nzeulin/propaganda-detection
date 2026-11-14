"""Run an optional second pass over a completed analysis."""

from fastapi import APIRouter

from app.content.attribution_review import AttributionReviewInput, AttributionReviewReport, review_attribution

router = APIRouter(prefix="/api/v1")


@router.post("/attribution-review", response_model=AttributionReviewReport)
def attribution_review(body: AttributionReviewInput):
    return review_attribution(body)
