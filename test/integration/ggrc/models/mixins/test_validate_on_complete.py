# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for ValidateOnComplete mixin"""

from ggrc.models.assessment import Assessment
from ggrc.models.exceptions import ValidationError
from integration.ggrc import generator
from integration.ggrc import TestCase
from integration.ggrc.models import factories

GENERATOR = generator.ObjectGenerator()


# pylint: disable=too-many-instance-attributes
class CustomAttributeMock(object):
  """Defines CustomAttributeDefinition and CustomAttributeValue objects"""

  # pylint: disable=too-many-arguments
  def __init__(self, attributable, attribute_type="Text", mandatory=False,
               dropdown_parameters=None, global_=False, value=None):
    self.attributable = attributable
    self.attribute_type = attribute_type
    self.mandatory = mandatory
    self.dropdown_parameters = dropdown_parameters
    self.attribute_value = value
    self.global_ = global_
    self.definition = self.make_definition()
    self.value = self.make_value()

  def make_definition(self):
    """Generate a custom attribute definition."""
    definition = factories.CustomAttributeDefinitionFactory(
        attribute_type=self.attribute_type,
        definition_type=self.attributable.__class__.__name__,
        definition_id=None if self.global_ else self.attributable.id,
        mandatory=self.mandatory,
        multi_choice_options=(self.dropdown_parameters[0]
                              if self.dropdown_parameters else None),
        multi_choice_mandatory=(self.dropdown_parameters[1]
                                if self.dropdown_parameters else None),
    )
    return definition

  def make_value(self):
    """Generate a custom attribute value."""
    if self.attribute_value is not None:
      value = factories.CustomAttributeValueFactory(
          custom_attribute_id=self.definition.id,
          attributable_type=self.attributable.__class__.__name__,
          attributable_id=self.attributable.id,
          attribute_value=self.attribute_value,
      )
    else:
      value = None
    return value


class TestValidateOnComplete(TestCase):
  """Integration tests suite for ValidateOnComplete mixin"""

  # pylint: disable=invalid-name

  def setUp(self):
    super(TestValidateOnComplete, self).setUp()
    self.assessment = factories.AssessmentFactory(
        status=Assessment.PROGRESS_STATE,
    )

  def test_validates_with_no_ca(self):
    """Validation ok with no CA restrictions."""
    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_no_mandatory_ca(self):
    """Validation ok with no CA-introduced restrictions."""
    CustomAttributeMock(self.assessment, attribute_type="Text")
    CustomAttributeMock(self.assessment, attribute_type="Checkbox")

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_mandatory_empty_ca(self):
    """Validation fails if mandatory CA is empty."""
    CustomAttributeMock(self.assessment, mandatory=True)

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  def test_validates_with_mandatory_filled_ca(self):
    """Validation ok if mandatory CA is filled."""
    CustomAttributeMock(self.assessment, mandatory=True, value="Foo")

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_mandatory_empty_global_ca(self):
    """Validation fails if global mandatory CA is empty."""
    CustomAttributeMock(self.assessment, mandatory=True, global_=True)

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  def test_validates_with_mandatory_filled_global_ca(self):
    """Validation ok if global mandatory CA is filled."""
    CustomAttributeMock(self.assessment, mandatory=True, global_=True,
                        value="Foo")

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_missing_mandatory_comment(self):
    """Validation fails if comment required by CA is missing."""
    CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value="comment_required",
    )

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  def test_validates_with_present_mandatory_comment(self):
    """Validation ok if comment required by CA is present."""
    ca = CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value=None,  # the value is made with generator to store revision too
    )
    _, ca.value = GENERATOR.generate_custom_attribute_value(
        custom_attribute_id=ca.definition.id,
        attributable=self.assessment,
        attribute_value="comment_required",
    )
    comment = factories.CommentFactory(
        assignee_type="Assessor",
        description="Mandatory comment",
    )
    comment.custom_attribute_revision_upd({
        "custom_attribute_revision_upd": {
            "custom_attribute_value": {
                "id": ca.value.id,
            },
        },
    })
    factories.RelationshipFactory(
        source=self.assessment,
        destination=comment,
    )

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)
