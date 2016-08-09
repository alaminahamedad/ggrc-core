# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Contains ValidateOnComplete mixin.

This defines a procedure of an object's validation when its status moves from
one of NOT_DONE_STATES to DONE_STATES.
"""

from sqlalchemy.orm import validates

from ggrc.models.exceptions import ValidationError


class ValidateOnComplete(object):
  """Defines the validation routine before marking an object as complete.

  Requires Stateful and Statusable to be mixed in as well."""

  # pylint: disable=too-few-public-methods

  @validates("status")
  def validate_status(self, key, value):
    """Check that no CA-introduced completion preconditions are missing."""
    # support for multiple validators for status
    if hasattr(super(ValidateOnComplete, self), "validate_status"):
      value = super(ValidateOnComplete, self).validate_status(key, value)

    if self.status in self.NOT_DONE_STATES and value in self.DONE_STATES:
      if hasattr(self, "preconditions_failed") and self.preconditions_failed:
        raise ValidationError("CA-introduced completion preconditions "
                              "are not satisfied. Check preconditions_failed "
                              "of items of self.custom_attribute_values")

    return value
