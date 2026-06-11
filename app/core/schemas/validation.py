from pydantic import BaseModel, ConfigDict, model_validator


class NonEmptyUpdateMixin(BaseModel):
    """Shared base for partial-PATCH update request schemas.

    - ``extra="forbid"``: unknown request fields are rejected with 422 instead
      of being silently ignored, so removed/renamed fields surface as contract
      drift rather than being swallowed.
    - Requires at least one field to be present, so an empty ``{}`` PATCH body
      returns 422. Presence is checked via ``model_fields_set`` (not
      ``exclude_none``) because an explicit ``null`` is a valid change for
      nullable fields.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("יש לשלוח לפחות שדה אחד לעדכון")
        return self
