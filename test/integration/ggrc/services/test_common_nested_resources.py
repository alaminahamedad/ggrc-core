# Copyright (C) 2016 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: aleh_rymasheuski@epam.com
# Maintained By: aleh_rymasheuski@epam.com

"""
Test REST API calls for nested resources
"""

# pylint: disable=invalid-name
# pylint: disable=super-on-old-class
# pylint: disable=too-few-public-methods

from ggrc import app
from ggrc import db
from ggrc.models.mixins import Base
from ggrc.services.common import Resource
from integration.ggrc import TestCase
from integration.ggrc.api_helper import Api
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc.services import model_registered


class OuterModel(Base, db.Model):
  """First part of /api/{outer_model}/{id}/{inner_model} address"""
  __tablename__ = 'outer_model'
  title = db.Column(db.String)

  _publish_attrs = ['modified_by_id', 'title']
  _update_attrs = ['title']
  _fulltext_attrs = ['title']


class InnerModel(Base, db.Model):
  """Last part of /api/{outer_model}/{id}/{inner_model} address"""
  __tablename__ = 'inner_model'
  title = db.Column(db.String)

  _publish_attrs = ['modified_by_id', 'title']
  _update_attrs = ['title']
  _fulltext_attrs = ['title']


class TestNestedResources(TestCase):
  """Test requests to endpoints like '/audits/1/assessments'"""

  managed_models = [OuterModel, InnerModel]

  COLLECTION_URL = '/api/{model}'
  OBJECT_URL = '/api/{obj_model}/{obj_id}'
  NESTED_OBJECT_URL = '{}/{{inner_obj_model}}'.format(OBJECT_URL)

  @classmethod
  def setUpClass(cls):
    super(TestNestedResources, cls).setUpClass()
    for model in cls.managed_models:
      Resource.add_to(
        app.app,
        cls.COLLECTION_URL.format(model=model.__tablename__),
        model_class=model,
      )

  def setUp(self):
    super(TestNestedResources, self).setUp()
    for model in self.managed_models:
      model.__table__.create(db.engine, checkfirst=True)

    self.object_generator = ObjectGenerator()
    self.client.get('/login')
    self.api = Api()

  def tearDown(self):
    super(TestNestedResources, self).tearDown()
    # Explicitly destroy test tables
    # Note: This must be after the 'super()', because the session is
    #   closed there.  (And otherwise it might stall due to locks).
    for model in reversed(self.managed_models):
      model.__table__.drop(db.engine, checkfirst=True)

  @classmethod
  def mock_url(cls, obj, inner_class=None, override=None):
    """Make a mock url to a certain object (optionally to its nested model)"""
    if override is None:
      override = {}
    parameters = {
      'obj_model': type(obj).__tablename__,
      'obj_id': obj.id,
    }
    if inner_class is None:
      # url for a single object
      url = cls.OBJECT_URL
    else:
      # url for nested objects
      url = cls.NESTED_OBJECT_URL
      parameters['inner_obj_model'] = inner_class.__tablename__

    parameters.update(override)
    return url.format(**parameters)

  @staticmethod
  def parse_response(response, inner_class):
    """Fetch collection dict and models list from a json response"""
    model_name = inner_class.__tablename__
    collection_name = '{}_collection'.format(model_name)

    collection = response.json[collection_name]
    models = collection[model_name]
    return models, collection

  def make_outer_and_inner(self, outer_data=None, inner_data=None):
    """Create OuterModel and InnerModel instances and a relationship between"""
    _, outer = self.object_generator.generate_object(OuterModel,
                                                     data=outer_data)
    _, inner = self.object_generator.generate_object(InnerModel,
                                                     data=inner_data)
    self.object_generator.generate_relationship(outer, inner)
    return outer, inner

  def test_get(self):
    """Test get nested object collection"""
    outer, inner = self.make_outer_and_inner()

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=InnerModel)

    self.assertEqual(len(models), 1)
    self.assertEqual(models[0]['id'], inner.id)
    self.assertEqual(models[0]['title'], inner.title)

  def test_get_multiple_results(self):
    """Test get nested object collection with several items"""
    _, outer = self.object_generator.generate_object(OuterModel)

    inner_objects_count = 5
    ids_titles = []
    for _ in range(inner_objects_count):
      _, inner = self.object_generator.generate_object(InnerModel)
      self.object_generator.generate_relationship(outer, inner)
      ids_titles.append((inner.id, inner.title))

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=InnerModel)

    def id_title_key(id_title_tuple):
      return id_title_tuple[0]

    self.assertEqual(len(models), inner_objects_count)
    self.assertListEqual(
      sorted([(model['id'], model['title']) for model in models],
             key=id_title_key),
      sorted(ids_titles,
             key=id_title_key),
    )

  def test_get_no_results(self):
    """Test get nested object collection with no items"""
    _, outer = self.object_generator.generate_object(OuterModel)

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=InnerModel)

    self.assertListEqual(models, [])

  def test_get_reverse_relationship(self):
    """Test get nested object collection with reversed relation direction"""
    outer, inner = self.make_outer_and_inner()

    # "inner" and "outer" are swapped in this test intentionally
    response = self.client.get(
      self.mock_url(obj=inner, inner_class=OuterModel),
    )

    self.assert200(response)
    models, _ = self.parse_response(response=response, inner_class=OuterModel)

    self.assertEqual(len(models), 1)
    self.assertEqual(models[0]['id'], outer.id)
    self.assertEqual(models[0]['title'], outer.title)

  def test_get_bad_accept(self):
    """Check that nested resource GET requires Accept header"""
    outer, _ = self.make_outer_and_inner()

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel),
      headers={'Accept': 'text/plain'},
    )

    self.assertStatus(response, 406)
    self.assertEqual(response.headers.get('Content-Type'), 'text/plain')
    self.assertEqual(response.data, 'application/json')

  def test_get_invalid_id(self):
    """Check that nested resource GET returns 404 with invalid outer obj id"""
    outer, _ = self.make_outer_and_inner()

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel,
                    override={'obj_id': 'text is not acceptable'}),
    )

    self.assert404(response)

  def test_get_missing_id(self):
    """Check that nested resource GET returns 404 when outer obj is missing"""
    outer, _ = self.make_outer_and_inner()

    response = self.client.get(
      self.mock_url(obj=outer, inner_class=InnerModel,
                    # assume there is no item with this id
                    override={'obj_id': 99999}),
    )

    self.assert404(response)

  def test_get_invalid_inner_class(self):
    """Check that nested resource GET returns 404 with invalid inner class"""
    class InvalidInnerClassModel(object):
      __tablename__ = 'there_should_be_no_such_model'

    _, outer = self.object_generator.generate_object(OuterModel)

    response = self.client.get(
      self.mock_url(obj=outer,
                    inner_class=InvalidInnerClassModel),
    )

    self.assert404(response)

  def test_get_search(self):
    """Check that search works with nested resources"""
    outer, inner = self.make_outer_and_inner(inner_data={'title': 'foo'})

    with model_registered(InnerModel):

      response = self.client.get(
        (self.mock_url(obj=outer,
                       inner_class=InnerModel) +
         '?__search=title={}'.format(inner.title)),
      )

    self.assert200(response)
    models, _ = self.parse_response(response, InnerModel)

    self.assertEqual(len(models), 1)
    self.assertEqual(models[0]['id'], inner.id)
    self.assertEqual(models[0]['title'], inner.title)

  def test_get_sort(self):
    """Check that sorting works with nested resources"""
    objects = [self.object_generator.generate_object(OuterModel)[1]
               for _ in range(10)]
    titles = [obj.title for obj in objects]

    def check_sort_order(sort_parameters, expected_titles):
      """Check that sorting with sort_parameters results in correct order"""
      response = self.client.get('/api/{model}?{param}'
                                 .format(model=OuterModel.__tablename__,
                                         param=sort_parameters))

      resp_models, _ = self.parse_response(response, OuterModel)
      resp_titles = [obj['title'] for obj in resp_models]

      self.assertListEqual(resp_titles, expected_titles)

    cases = (
      ('__sort=title', sorted(titles)),
      ('__sort=-title', sorted(titles, reverse=True)),
      ('__sort=title&__sort_desc=false', sorted(titles)),
      ('__sort=-title&__sort_desc=false', sorted(titles, reverse=True)),
      ('__sort=title&__sort_desc=true', sorted(titles, reverse=True)),
      ('__sort=-title&__sort_desc=true', sorted(titles)),
    )
    for sort_parameters, expected_titles in cases:
      check_sort_order(sort_parameters, expected_titles)
