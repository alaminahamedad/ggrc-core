# Copyright (C) 2013 Google Inc., authors, and contributors <see AUTHORS file>
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
# Created By: david@reciprocitylabs.com
# Maintained By: david@reciprocitylabs.com

from ggrc import db
from ggrc.login import get_current_user
from ggrc.models import all_models
from ggrc.models.object_person import ObjectPerson
from ggrc.models.object_owner import ObjectOwner
from ggrc.models.relationship import Relationship
from ggrc_basic_permissions.models import UserRole
from ggrc_basic_permissions import objects_via_assignable_query
from ggrc_basic_permissions import program_relationship_query
from ggrc_basic_permissions import backlog_workflows
from ggrc.rbac import permissions, context_query_filter
from sqlalchemy import \
    event, and_, or_, literal, union, alias, case, func, distinct
from sqlalchemy.sql import false
from sqlalchemy.schema import DDL
from sqlalchemy.ext.declarative import declared_attr
from .sql import SqlIndexer


class MysqlRecordProperty(db.Model):
  __tablename__ = 'fulltext_record_properties'

  key = db.Column(db.Integer, primary_key=True)
  type = db.Column(db.String(64), primary_key=True)
  context_id = db.Column(db.Integer)
  tags = db.Column(db.String)
  property = db.Column(db.String(64), primary_key=True)
  content = db.Column(db.Text)

  @declared_attr
  def __table_args__(self):
    return (
        # NOTE
        # This is here to prevent Alembic from wanting to drop the index, but
        # the DDL below or a similar Alembic migration should be used to create
        # the index.
        db.Index('{}_text_idx'.format(self.__tablename__), 'content'),
        # These are real indexes
        db.Index('ix_{}_key'.format(self.__tablename__), 'key'),
        db.Index('ix_{}_type'.format(self.__tablename__), 'type'),
        db.Index('ix_{}_tags'.format(self.__tablename__), 'tags'),
        db.Index('ix_{}_context_id'.format(self.__tablename__), 'context_id'),
        # Only MyISAM supports fulltext indexes until newer MySQL/MariaDB
        {'mysql_engine': 'myisam'},
    )

event.listen(
    MysqlRecordProperty.__table__,
    'after_create',
    DDL('ALTER TABLE {tablename} ADD FULLTEXT INDEX {tablename}_text_idx '
        '(content)'.format(tablename=MysqlRecordProperty.__tablename__))
)


class MysqlIndexer(SqlIndexer):
  record_type = MysqlRecordProperty

  # the fields in which a search will be performed if none provided
  _default_search_fields_raw = ['title', 'name', 'email', 'notes',
                                'description', 'slug']

  def _get_type_query(self, model_names, permission_type='read',
                      permission_model=None):

    type_queries = []
    for model_name in model_names:
      type_query = None
      if permission_type == 'read':
        contexts = permissions.read_contexts_for(
            permission_model or model_name)
        resources = permissions.read_resources_for(
            permission_model or model_name)
      elif permission_type == 'create':
        contexts = permissions.create_contexts_for(
            permission_model or model_name)
        resources = permissions.create_resources_for(
            permission_model or model_name)
      elif permission_type == 'update':
        contexts = permissions.update_contexts_for(
            permission_model or model_name)
        resources = permissions.update_resources_for(
            permission_model or model_name)
      elif permission_type == 'delete':
        contexts = permissions.delete_contexts_for(
            permission_model or model_name)
        resources = permissions.delete_resources_for(
            permission_model or model_name)

      if permission_model and contexts:
        contexts = set(contexts) & set(
            permissions.read_contexts_for(model_name))

      if contexts is not None:
        # Don't filter out None contexts here
        if None not in contexts and permission_type == "read":
          contexts.append(None)

        if resources:
          resource_sql = and_(
              MysqlRecordProperty.type == model_name,
              MysqlRecordProperty.key.in_(resources))
        else:
          resource_sql = false()

        type_query = or_(
            and_(
                MysqlRecordProperty.type == model_name,
                context_query_filter(MysqlRecordProperty.context_id, contexts)
            ),
            resource_sql)
        type_queries.append(type_query)
      else:
        type_queries.append(MysqlRecordProperty.type == model_name)

    return and_(
        MysqlRecordProperty.type.in_(model_names),
        or_(*type_queries))

  def _get_filter_query(self, terms):
    """Parse `__search` query terms, return an SqlAlchemy filtering clause.

    Supported syntax:
      <terms> ::= <value> |  # any indexed field contains `value`
                  <field_name> = <value> |  # `field_name` value
                                            # is exactly `value`
                  <field_name> != <value>  # `field_name` value
                                           # is not exactly `value`
      <value> ::= <any sequence not containing = sign>
      <field_name> ::= <indexed field name>
    `field_name` should be equal to a name of an indexed field for the queried
    type of object
    """
    # Note: This is an incomplete search syntax, much simpler than the
    # documented functionality: ~, !~, <, >, compound clauses (AND, OR)
    # are not implemented yet.
    if not terms:
      filters = self._default_search_fields()
    elif '!=' in terms:
      column_name, value = terms.split('!=', 1)
      value = value.strip('"')
      filters = and_(
          self.record_type.property == column_name.strip().lower(),
          self.record_type.content != value.strip().lower(),
      )
    elif '=' in terms:
      column_name, value = terms.split('=', 1)
      value = value.strip('"')
      filters = and_(
          self.record_type.property == column_name.strip().lower(),
          self.record_type.content == value.strip().lower(),
      )
    else:
      filters = and_(self._default_search_fields(),
                     self.record_type.content.contains(terms))

    # FIXME: Temporary (slow) fix for words shorter than MySQL default limit
    # elif len(terms) < 4:
    #   return MysqlRecordProperty.content.contains(terms)
    # else:
    #   return MysqlRecordProperty.content.match(terms)
    return filters

  def _default_search_fields(self):
    return or_(
        # Because property values for custom attributes are
        # `attribute_value_<id>`
        self.record_type.property.contains('attribute_value'),
        self.record_type.property.in_(self._default_search_fields_raw),
    )

  def _get_type_select_column(self, model):
    mapper = model._sa_class_manager.mapper
    if mapper.polymorphic_on is None:
      type_column = literal(mapper.class_.__name__)
    else:
      # Handle polymorphic types with CASE
      type_column = case(
          value=mapper.polymorphic_on,
          whens={
              val: m.class_.__name__
              for val, m in mapper.polymorphic_map.items()
          })
    return type_column

  def _types_to_type_models(self, types):
    if types is None:
      return all_models.all_models
    return [m for m in all_models.all_models if m.__name__ in types]

  # filters by "myview" for a given person
  def _add_owner_query(self, query, types=None, contact_id=None):  # noqa
    '''
    Finds all objects which might appear on a user's Profile or Dashboard
    pages, including:

      Objects mapped via ObjectPerson
      Objects owned via ObjectOwner
      Objects in private contexts via UserRole (e.g. for Private Programs)
      Objects for which the user is the "contact"
      Objects for which the user is the "primary_assessor" or
        "secondary_assessor"
      Objects to which the user is mapped via a custom attribute
      Assignable objects for which the user is an assignee

    This method only *limits* the result set -- Contexts and Roles will still
    filter out forbidden objects.
    '''

    # Check if the user has Creator role
    current_user = get_current_user()
    my_objects = contact_id is not None
    if current_user.system_wide_role == "Creator":
      contact_id = current_user.id

    if not contact_id:
      return query

    type_models = self._types_to_type_models(types)

    model_names = [model.__name__ for model in type_models]

    models = []
    for model in type_models:
      base_model = model._sa_class_manager.mapper.primary_base_mapper.class_
      if base_model not in models:
        models.append(base_model)

    models = [(model, self._get_type_select_column(model)) for model in models]

    type_union_queries = []

    all_people = db.session.query(
        all_models.Person.id.label('id'),
        literal(all_models.Person.__name__).label('type'),
        literal(None).label('context_id')
    )
    type_union_queries.append(all_people)

    # Objects to which the user is "mapped"
    # We don't return mapped objects for the Creator because being mapped
    # does not give the Creator necessary permissions to view the object.
    if current_user.system_wide_role != "Creator":
      object_people_query = db.session.query(
          ObjectPerson.personable_id.label('id'),
          ObjectPerson.personable_type.label('type'),
          literal(None).label('context_id')
      ).filter(
          and_(
              ObjectPerson.person_id == contact_id,
              ObjectPerson.personable_type.in_(model_names)
          )
      )
      type_union_queries.append(object_people_query)

    # Objects for which the user is an "owner"
    object_owners_query = db.session.query(
        ObjectOwner.ownable_id.label('id'),
        ObjectOwner.ownable_type.label('type'),
        literal(None).label('context_id')
    ).filter(
        and_(
            ObjectOwner.person_id == contact_id,
            ObjectOwner.ownable_type.in_(model_names),
        )
    )
    type_union_queries.append(object_owners_query)

    # Objects to which the user is mapped via a custom attribute
    ca_mapped_objects_query = db.session.query(
        all_models.CustomAttributeValue.attributable_id.label('id'),
        all_models.CustomAttributeValue.attributable_type.label('type'),
        literal(None).label('context_id')
    ).filter(
        and_(
            all_models.CustomAttributeValue.attribute_value == "Person",
            all_models.CustomAttributeValue.attribute_object_id == contact_id
        )
    )
    type_union_queries.append(ca_mapped_objects_query)

    # Objects for which the user is assigned
    model_assignee_query = db.session.query(
        Relationship.destination_id.label('id'),
        Relationship.destination_type.label('type'),
        literal(None).label('context_id'),
    ).filter(
        and_(
            Relationship.source_type == "Person",
            Relationship.source_id == contact_id,
        ),
    )
    type_union_queries.append(model_assignee_query)

    model_assignee_query = db.session.query(
        Relationship.source_id.label('id'),
        Relationship.source_type.label('type'),
        literal(None).label('context_id'),
    ).filter(
        and_(
            Relationship.destination_type == "Person",
            Relationship.destination_id == contact_id,
        ),
    )
    type_union_queries.append(model_assignee_query)

    if not my_objects:
      type_union_queries.append(
          program_relationship_query(contact_id, True))
      type_union_queries.append(
          objects_via_assignable_query(contact_id)
      )
    # also show backlog workflows
    type_union_queries.append(backlog_workflows())

    # FIXME The following line crashes if the Workflow extension is not enabled
    for model in [all_models.Program, all_models.Audit, all_models.Workflow]:
      context_query = db.session.query(
          model.id.label('id'),
          literal(model.__name__).label('type'),
          literal(None).label('context_id'),
      ).join(
          UserRole,
          and_(
              UserRole.context_id == model.context_id,
              UserRole.person_id == contact_id,
          )
      )
      type_union_queries.append(context_query)

    for model, type_column in models:
      # Objects for which the user is the "contact" or "secondary contact"
      if hasattr(model, 'contact_id'):
        model_type_query = db.session.query(
            model.id.label('id'),
            type_column.label('type'),
            literal(None).label('context_id')
        ).filter(
            model.contact_id == contact_id
        ).distinct()
        type_union_queries.append(model_type_query)
      # Objects for which the user is the "contact"
      if hasattr(model, 'secondary_contact_id'):
        model_type_query = db.session.query(
            model.id.label('id'),
            type_column.label('type'),
            literal(None).label('context_id')
        ).filter(
            model.secondary_contact_id == contact_id
        ).distinct()
        type_union_queries.append(model_type_query)

      if model is all_models.Control:
        # Control also has `principal_assessor` and `secondary_assessor`
        assessor_queries = []
        if hasattr(model, 'principal_assessor_id'):
          assessor_queries.append(or_(
              model.principal_assessor_id == contact_id))
        if hasattr(model, 'secondary_assessor_id'):
          assessor_queries.append(or_(
              model.secondary_assessor_id == contact_id))

        model_type_query = db.session.query(
            model.id.label('id'),
            type_column.label('type'),
            literal(None).label('context_id')
        ).filter(
            or_(*assessor_queries)
        ).distinct()
        type_union_queries.append(model_type_query)

    # Construct and JOIN to the UNIONed result set
    type_union_query = alias(union(*type_union_queries))
    query = query.join(
        type_union_query,
        and_(
            type_union_query.c.id == MysqlRecordProperty.key,
            type_union_query.c.type == MysqlRecordProperty.type),
    )

    return query

  def _add_extra_params_query(self, query, type, extra_param):
    if not extra_param:
      return query

    models = [m for m in all_models.all_models if m.__name__ == type]

    if len(models) == 0:
      return query
    model = models[0]

    return query.filter(self.record_type.key.in_(
        db.session.query(
            model.id.label('id')
        ).filter_by(**extra_param)
    ))

  def _get_grouped_types(self, types, extra_params=None):
    model_names = [model.__name__ for model in all_models.all_models]
    if types is not None:
      model_names = [m for m in model_names if m in types]

    if extra_params is not None:
      model_names = [m for m in model_names if m not in extra_params]
    return model_names

  def search(self, terms, types=None, permission_type='read',
             permission_model=None, contact_id=None, extra_params={}):
    model_names = self._get_grouped_types(types, extra_params)
    query = db.session.query(
        self.record_type.key, self.record_type.type,
        self.record_type.property, self.record_type.content)
    query = query.filter(
        self._get_type_query(model_names, permission_type, permission_model))
    query = query.filter(self._get_filter_query(terms))
    query = self._add_owner_query(query, types, contact_id)

    model_names = [model.__name__ for model in all_models.all_models]
    if types is not None:
      model_names = [m for m in model_names if m in types]

    unions = []
    # Add extra_params and extra_colums:
    for k, v in extra_params.iteritems():
      if k not in model_names:
        continue
      q = db.session.query(
          self.record_type.key, self.record_type.type,
          self.record_type.property, self.record_type.content)
      q = q.filter(
          self._get_type_query([k], permission_type, permission_model))
      q = q.filter(self._get_filter_query(terms))
      q = self._add_owner_query(q, [k], contact_id)
      q = self._add_extra_params_query(q, k, v)
      unions.append(q)
    # Sort by title:
    # FIXME: This only orders by `title` if title was the matching property
    query = query.union(*unions)
    query = query.order_by(case(
        [(self.record_type.property == "title", self.record_type.content)],
        else_=literal("ZZZZZ")))
    return query

  def counts(self, terms, group_by_type=True, types=None, contact_id=None,
             extra_params={}, extra_columns={}):
    model_names = self._get_grouped_types(types, extra_params)
    query = db.session.query(
        self.record_type.type, func.count(distinct(
            self.record_type.key)), literal(""))
    query = query.filter(self._get_type_query(model_names))
    query = query.filter(self._get_filter_query(terms))
    query = self._add_owner_query(query, types, contact_id)
    query = query.group_by(self.record_type.type)
    all_extra_columns = dict(extra_columns.items() +
                             [(p, p) for p in extra_params
                              if p not in extra_columns])
    if not all_extra_columns:
      return query.all()

    # Add extra_params and extra_colums:
    for k, v in all_extra_columns.iteritems():
      q = db.session.query(
          self.record_type.type, func.count(
              distinct(self.record_type.key)), literal(k))
      q = q.filter(self._get_type_query([v]))
      q = q.filter(self._get_filter_query(terms))
      q = self._add_owner_query(q, [v], contact_id)
      q = self._add_extra_params_query(q, v, extra_params.get(k, None))
      q = q.group_by(self.record_type.type)
      query = query.union(q)
    return query.all()

Indexer = MysqlIndexer
