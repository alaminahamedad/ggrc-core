# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for ValidateOnComplete mixin"""

from ggrc.models.assessment import Assessment
from ggrc.models.exceptions import ValidationError
from integration.ggrc import TestCase
from integration.ggrc.models import factories


# pylint: disable=super-on-old-class; TestCase is a new-style class
class TestValidateOnComplete(TestCase):
  """Integration tests suite for ValidateOnComplete mixin"""

  # pylint: disable=invalid-name

  def setUp(self):
    super(TestValidateOnComplete, self).setUp()
    self.assessment = factories.AssessmentFactory(
        status=Assessment.PROGRESS_STATE,
    )

  def make_custom_attribute_definition(self, mandatory):
    return factories.CustomAttributeDefinitionFactory(
        attribute_type="Text",
        definition_type="Assessment",
        definition_id=self.assessment.id,
        mandatory=mandatory
    )

  def test_validates_with_no_mandatory_ca(self):
    """Validation ok with no CA-introduced restrictions."""
    self.make_custom_attribute_definition(mandatory=False)

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_mandatory_empty_ca(self):
    """Validation fails if mandatory CA is empty."""
    self.make_custom_attribute_definition(mandatory=True)

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  # most of the test cases were moved to TestPreconditionsFailed since
  # ValidateOnComplete logic depends on preconditions_failed flags
