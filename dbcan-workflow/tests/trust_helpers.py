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
