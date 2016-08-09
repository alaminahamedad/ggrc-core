# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for ValidateOnComplete mixin"""

from ggrc import db
from ggrc.models.assessment import Assessment
from ggrc.models.exceptions import ValidationError
from integration.ggrc import generator
from integration.ggrc import TestCase


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
    _, definition = GENERATOR.generate_custom_attribute(
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
      _, value = GENERATOR.generate_custom_attribute_value(
          custom_attribute_id=self.definition.id,
          attributable=self.attributable,
          attribute_value=self.attribute_value,
      )
    else:
      value = None
    return value


class TestValidateOnComplete(TestCase):
  """Integration tests suite for ValidateOnComplete mixin"""

  # pylint: disable=invalid-name

  @staticmethod
  def create_assessment():
    """Generate an assessment with mapped custom attributes."""
    _, assessment = GENERATOR.generate_object(
        Assessment,
        data={
            "status": Assessment.PROGRESS_STATE,
        },
    )
    return assessment

  @staticmethod
  def refresh(obj):
    db.session.add(obj)
    db.session.refresh(obj)

  def setUp(self):
    super(TestValidateOnComplete, self).setUp()
    self.assessment = self.create_assessment()

  def test_validates_with_no_ca(self):
    """Validation ok with no CA restrictions."""
    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_no_mandatory_ca(self):
    """Validation ok with no CA-introduced restrictions."""
    CustomAttributeMock(self.assessment, attribute_type="Text")
    CustomAttributeMock(self.assessment, attribute_type="Checkbox")
    self.refresh(self.assessment)

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_mandatory_empty_ca(self):
    """Validation fails if mandatory CA is empty."""
    CustomAttributeMock(self.assessment, mandatory=True)
    self.refresh(self.assessment)

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  def test_validates_with_mandatory_filled_ca(self):
    """Validation ok if mandatory CA is filled."""
    CustomAttributeMock(self.assessment, mandatory=True, value="Foo")
    self.refresh(self.assessment)

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_validates_with_mandatory_empty_global_ca(self):
    """Validation fails if global mandatory CA is empty."""
    CustomAttributeMock(self.assessment, mandatory=True, global_=True)
    self.refresh(self.assessment)

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  def test_validates_with_mandatory_filled_global_ca(self):
    """Validation ok if global mandatory CA is filled."""
    CustomAttributeMock(self.assessment, mandatory=True, global_=True,
                        value="Foo")
    self.refresh(self.assessment)

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
    self.refresh(self.assessment)

    with self.assertRaises(ValidationError):
      self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.PROGRESS_STATE)

  def test_validates_with_present_mandatory_comment(self):
    """Validation ok if comment required by CA is present."""
    ca = CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value="comment_required",
    )
    _, comment = GENERATOR.generate_comment(
        commentable=self.assessment,
        assignee_type="Assessor",
        description="Mandatory comment",
        custom_attribute_revision_upd={
            "custom_attribute_value": {
                "id": ca.value.id,
            },
        },
    )
    GENERATOR.generate_relationship(self.assessment, comment)
    self.refresh(self.assessment)

    self.assessment.status = self.assessment.FINAL_STATE

    self.assertEqual(self.assessment.status, self.assessment.FINAL_STATE)

  def test_preconditions_failed_with_no_ca(self):
    """No preconditions failed with no CA restrictions."""
    preconditions_failed = self.assessment.preconditions_failed

    self.assertFalse(preconditions_failed)

  def test_preconditions_failed_with_no_mandatory_ca(self):
    """No preconditions failed with no CA-introduced restrictions."""
    CustomAttributeMock(self.assessment, attribute_type="Text")
    CustomAttributeMock(self.assessment, attribute_type="Checkbox")
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertFalse(preconditions_failed)

  def test_preconditions_failed_with_mandatory_empty_ca(self):
    """Some preconditions failed if mandatory CA is empty."""
    ca = CustomAttributeMock(self.assessment, mandatory=True)
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed,
                     {ca.definition.id: ["value"]})

  def test_preconditions_failed_with_mandatory_filled_ca(self):
    """No preconditions failed if mandatory CA is filled."""
    CustomAttributeMock(self.assessment, mandatory=True, value="Foo")
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertFalse(preconditions_failed)

  def test_preconditions_failed_with_mandatory_empty_global_ca(self):
    """Some preconditions failed if global mandatory CA is empty."""
    ca = CustomAttributeMock(self.assessment, mandatory=True, global_=True)
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed,
                     {ca.definition.id: ["value"]})

  def test_preconditions_failed_with_mandatory_filled_global_ca(self):
    """No preconditions failed if global mandatory CA is filled."""
    CustomAttributeMock(self.assessment, mandatory=True, global_=True,
                        value="Foo")
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertFalse(preconditions_failed)

  def test_preconditions_failed_with_missing_mandatory_comment(self):
    """Some preconditions failed if comment required by CA is missing."""
    ca = CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value="comment_required",
    )
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed,
                     {ca.definition.id: ["comment"]})

  def test_preconditions_failed_with_present_mandatory_comment(self):
    """No preconditions failed if comment required by CA is present."""
    ca = CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value="comment_required",
    )
    _, comment = GENERATOR.generate_comment(
        commentable=self.assessment,
        assignee_type="Assessor",
        description="Mandatory comment",
        custom_attribute_revision_upd={
            "custom_attribute_value": {
                "id": ca.value.id,
            },
        },
    )
    GENERATOR.generate_relationship(self.assessment, comment)
    self.refresh(self.assessment)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertFalse(preconditions_failed)
