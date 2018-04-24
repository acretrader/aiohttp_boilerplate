import json
import warnings

from aiohttp import web

from .exceptions import JSONHTTPError


# Retrieve data from database and send to the client
# Schema is telling how to for transfer data from SQL to JSON format
class OptionsView(web.View):
    """ Base class have implementation of the 'OPTIONS' method
        Class provide isamorphic way to do validation for front/backed
    """

    def __init__(self, request):
        super().__init__(request)
        self.request_raw_data = None

    # On start will always run before any other methods
    async def on_start(self):
        pass

    # Read data from request and save in request_raw_data
    async def get_request_data(self, to_json=False):
        if self.request_raw_data is None:
            self.request_raw_data = await self.request.text()
        if to_json is True:
            json.loads(self.request_raw_data)

        return self.request_raw_data

    # Will return options request with fields meta data
    async def options(self):

        # Check if its CORS request from google chrome/firefox/edge return empty body
        if self.request.header.get("Accept") == "*/*":
            return web.response('')

        return web.json_response(self._fields(self.schema()) if self.schema else {})


# Options request with a schema data
class SchemaOptionsView(OptionsView):

    # ToDo
    # Read about * in python 3.6
    def __init__(self, request):
        super().__init__(request)
        self.schema = self.get_schema()

    def get_schema():
        warnings.warn('Redefine get_schema in inherited class', RuntimeWarning)
        return None

    # Will return options request with validation data for a frontend
    def _getValidation(self, field):
        rules = {}

        if field.validate:
            for v in field.validate:
                rules_name = v.__class__.__name__
                if rules_name == 'OneOf':
                    rules['oneOf'] = 'choices'
                    rules['choices'] = {}

                    for i, val in enumerate(v.choices):
                        try:
                            rules['choices'][val] = v.labels[i]
                        except IndexError:
                            rules['choices'][val] = val

                elif rules_name == 'Length':
                    if v.min:
                        rules['minLength'] = v.min
                    if v.max:
                        rules['maxLength'] = v.max

                elif rules_name == 'Range':
                    if v.min and v.max:
                        rules['range'] = [v.min, v.max]
                    if v.min:
                        rules['min'] = v.min
                    if v.max:
                        rules['max'] = v.max
                else:
                    rules['_' + rules_name] = rules_name
        return rules

    # Return fields information and validation data
    def _fields(self, schema):

        return {
            name: {
                'type': field.__class__.__name__.lower(),
                'many': field.many,
                'required': field.required,
                'schema': self._fields(field.schema),
            } if field.__class__.__name__.lower() == 'nested'
            else {
                'type': field.__class__.__name__.lower(),
                'validate': self._getValidation(field),
                'required': field.required
            } for name, field in schema.fields.items()}

    # Check if schema have NestedJoin Fields
    def schema_have_joins(self):
        schema = self.schema()
        for field in schema.fields:
            if schema.fields[field].__class__.__name__ == 'JoinNested':
                return True
        return False

    # Helper to convert data into beautifull json
    def join_prepare_fields(self, fields="*"):

        if fields == "*":
            fields = ""

        t_index = 1
        alias = {'t0': ''}

        sql = self.obj.sql
        if hasattr(self, 'objects'):
            sql = self.objects.sql

        sql.table = self.model.__table__ + """ as t0 """
        if self.schema:
            schema = self.schema()
            for name, field in sorted(schema.fields.items()):
                if field.__class__.__name__ == 'JoinNested':
                    sql.table += "{} {} as t{} on {}.{} ".format(
                        field.joinType,
                        field.table,
                        t_index,
                        't%d' % t_index,
                        field.joinOn
                    )
                    alias['t{}'.format(t_index)] = name
                    subs = field.nested()
                    for subf in subs.fields:
                        fields += ",t{}.{} as t{}__{}".format(
                            t_index,
                            subf,
                            t_index,
                            subf
                        )
                    t_index += 1
                else:
                    fields += ",t0.%s as t0__%s" % (name, name)

        fields = fields[1:]
        return (alias, fields)

    # Make beautiful json output
    def join_beautiful_output(self, aliases, raw_data):

        if raw_data is None:
            return {}

        temp = {}
        for k, v in aliases.items():
            if v != '':
                temp[v] = {}
        for k, v in raw_data.items():
            d = k.split('__')
            if aliases[d[0]] == '':
                temp[d[1]] = v
            else:
                temp[aliases[d[0]]][d[1]] = v

        return temp


# Options request for a signle object
class ObjectView(SchemaOptionsView):
    """ Base class have implementation to work with Single Object
        schema will be use to save or retrive data from database
        context will be to keep context of get requests
    """

    def __init__(self, request):
        super().__init__(request)

        self.id = None
        self.obj = self.get_model()

    # Return model object
    def get_model(self):
        warnings.warn('Redefine get_schema in inherited class', RuntimeWarning)
        return None

    # Return object id from request
    async def get_id(self):
        id = self.request.match_info.get('id')

        if id is None:
            raise JSONHTTPError({"__error__": "No id found"})
        # ToDo
        # Check if aiohttp can parse string/numeric data
        try:
            id = int(id)
        except ValueError:
            pass

        return id

    # Return context for and object
    async def get_data(self, raw_data):

        data = {}
        if self.schema:
            # ToDo
            # User schema loads
            for f in self.schema().fields:
                data[f] = raw_data.get(f)
        else:
            data = self.obj.data

        return data
