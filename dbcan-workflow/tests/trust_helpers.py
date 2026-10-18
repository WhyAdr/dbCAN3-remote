"""Reusable JSON-Pointer taint checks, including persisted command payloads."""
import json

def leaf_strings(value,pointer=''):
    if isinstance(value,str):yield pointer,value
    elif isinstance(value,dict):
        for key,child in value.items():
            escaped=str(key).replace('~','~0').replace('/','~1')
            yield from leaf_strings(child,pointer+'/'+escaped)
    elif isinstance(value,list):
        for index,child in enumerate(value):yield from leaf_strings(child,pointer+'/'+str(index))

def matches(pointer,pattern):
    path,parts=pointer.split('/')[1:],pattern.split('/')[1:]
    return len(path)>=len(parts) and all(a==b or b=='*' for a,b in zip(path,parts))

def check_taint(test,document,marker,paths,prefix=''):
    for pointer,text in leaf_strings(document,prefix):
        if marker in text:
            test.assertTrue(any(matches(pointer,p) for p in paths),pointer)
    # Root contract subtrees never carry user-controlled strings.
    if not prefix:
        for key in ('outcome','exit','evidence','claims'):
            test.assertNotIn(marker,json.dumps(document.get(key)))
        refusal=document.get('refusal') or {}
        for key in ('code','message','remediation','forbidden'):test.assertNotIn(marker,json.dumps(refusal.get(key)))
        for key in ('findings','warnings'):
            for row in document.get(key,[]):test.assertNotIn(marker,row['message'])

def validate_schema(value, schema, document=None, path=''):
    """Validate the JSON-Schema keywords used by this package, with stdlib only.

    This is scoped to the checked-in envelope schema, not a general validator.
    Unsupported keywords fail visibly rather than silently skipping validation.
    """
    import math,re
    document=schema if document is None else document
    if '$ref' in schema:
        target=document
        for key in schema['$ref'].removeprefix('#/').split('/'):target=target[key]
        return validate_schema(value,target,document,path)
    supported={'$schema','$id','$defs','type','required','additionalProperties','properties','items','enum','const',
               'oneOf','allOf','if','then','minimum','maxItems','maxLength','pattern'}
    assert set(schema)<=supported,('unsupported schema keywords',set(schema)-supported)
    def valid(candidate,rule):
        try:validate_schema(candidate,rule,document,path);return True
        except AssertionError:return False
    if 'const' in schema:assert value==schema['const'] and type(value) is type(schema['const']),(path,'const')
    if 'enum' in schema:assert value in schema['enum'],(path,'enum')
    if 'type' in schema:
        types=schema['type'] if isinstance(schema['type'],list) else [schema['type']]
        kinds={'null':value is None,'object':isinstance(value,dict),'array':isinstance(value,list),
               'string':isinstance(value,str),'boolean':type(value) is bool,'integer':type(value) is int,
               'number':type(value) in (int,float) and math.isfinite(value)}
        assert any(kinds[t] for t in types),(path,'type')
    if 'oneOf' in schema:assert sum(valid(value,r) for r in schema['oneOf'])==1,(path,'oneOf')
    for rule in schema.get('allOf',[]):validate_schema(value,rule,document,path)
    if 'if' in schema and valid(value,schema['if']) and 'then' in schema:validate_schema(value,schema['then'],document,path)
    if isinstance(value,dict):
        assert set(schema.get('required',[]))<=set(value),(path,'required')
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False:assert set(value)<=set(properties),(path,'additionalProperties')
        for key,child in value.items():
            if key in properties:validate_schema(child,properties[key],document,path+'/'+key)
    if isinstance(value,list):
        if 'maxItems' in schema:assert len(value)<=schema['maxItems'],(path,'maxItems')
        if 'items' in schema:
            for i,child in enumerate(value):validate_schema(child,schema['items'],document,path+'/'+str(i))
    if isinstance(value,str):
        if 'maxLength' in schema:assert len(value)<=schema['maxLength'],(path,'maxLength')
        if 'pattern' in schema:assert re.search(schema['pattern'],value),(path,'pattern')
    if type(value) in (int,float) and 'minimum' in schema:assert value>=schema['minimum'],(path,'minimum')
