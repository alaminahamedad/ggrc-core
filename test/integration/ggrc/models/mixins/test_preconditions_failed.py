# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for "preconditions_failed" CAV and CAable fields logic."""

from ggrc import db
from ggrc.models.assessment import Assessment
from integration.ggrc import TestCase
from integration.ggrc.models import factories


# pylint: disable=too-many-instance-attributes
class CustomAttributeMock(object):
  """Defines CustomAttributeDefinition and CustomAttributeValue objects"""

  # pylint: disable=too-many-arguments
  def __init__(self, attributable, attribute_type="Text", mandatory=False,
               dropdown_parameters=None, global_=False, value=""):
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
          attributable=self.attributable,
          attribute_value=self.attribute_value,
      )
    else:
      value = None
    return value


class TestPreconditionsFailed(TestCase):
  """Integration tests suite for preconditions_failed fields logic."""

  # pylint: disable=invalid-name

  def setUp(self):
    super(TestPreconditionsFailed, self).setUp()
    self.assessment = factories.AssessmentFactory(
        status=Assessment.PROGRESS_STATE,
    )

  def test_preconditions_failed_with_no_ca(self):
    """No preconditions failed with no CA restrictions."""
    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, False)

  def test_preconditions_failed_with_no_mandatory_ca(self):
    """No preconditions failed with no CA-introduced restrictions."""
    ca_text = CustomAttributeMock(self.assessment, attribute_type="Text")
    ca_cbox = CustomAttributeMock(self.assessment, attribute_type="Checkbox")

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, False)
    self.assertFalse(ca_text.value.preconditions_failed)
    self.assertFalse(ca_cbox.value.preconditions_failed)

  def test_preconditions_failed_with_mandatory_empty_ca(self):
    """Some preconditions failed if mandatory CA is empty."""
    ca = CustomAttributeMock(self.assessment, mandatory=True)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, True)
    self.assertEqual(ca.value.preconditions_failed,
                     ["value"])

  def test_preconditions_failed_with_mandatory_filled_ca(self):
    """No preconditions failed if mandatory CA is filled."""
    ca = CustomAttributeMock(self.assessment, mandatory=True, value="Foo")

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, False)
    self.assertFalse(ca.value.preconditions_failed)

  def test_preconditions_failed_with_mandatory_empty_global_ca(self):
    """Some preconditions failed if global mandatory CA is empty."""
    ca = CustomAttributeMock(self.assessment, mandatory=True, global_=True)

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, True)
    self.assertEqual(ca.value.preconditions_failed, ["value"])

  def test_preconditions_failed_with_mandatory_filled_global_ca(self):
    """No preconditions failed if global mandatory CA is filled."""
    ca = CustomAttributeMock(self.assessment, mandatory=True, global_=True,
                             value="Foo")

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, False)
    self.assertFalse(ca.value.preconditions_failed)

  def test_preconditions_failed_with_missing_mandatory_comment(self):
    """Some preconditions failed if comment required by CA is missing."""
    ca = CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value="comment_required",
    )

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, True)
    self.assertEqual(ca.value.preconditions_failed, ["comment"])

  def test_preconditions_failed_with_present_mandatory_comment(self):
    """No preconditions failed if comment required by CA is present."""
    ca = CustomAttributeMock(
        self.assessment,
        attribute_type="Dropdown",
        dropdown_parameters=("foo,comment_required", "0,1"),
        value="comment_required",
    )
    comment = factories.CommentFactory(
        assignee_type="Assessor",
        description="Mandatory comment",
        custom_attribute_revision_upd={
            "custom_attribute_value": {
                "id": ca.value.id,
            },
        },
    )
    factories.RelationshipFactory(
        source=self.assessment,
        destination=comment,
    )

    preconditions_failed = self.assessment.preconditions_failed

    self.assertEqual(preconditions_failed, False)
    self.assertFalse(ca.value.preconditions_failed)
