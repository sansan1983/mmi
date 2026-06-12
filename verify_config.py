import sys
sys.path.insert(0, r'F:\AI data\codex\mmi')

# Force reload from disk without any caching
import importlib, mmi.core.config as c
importlib.reload(c)

print("mask_ab:", repr(c.mask_api_key('sk-ab')))
print("mask_abcde:", repr(c.mask_api_key('sk-abcde')))
print("mask_abcdefg:", repr(c.mask_api_key('sk-abcdefg')))
print("mask_empty:", repr(c.mask_api_key('')))

# Test resolve_api_key fallback
c.set_llm_config(api_key='')
import os
os.environ['OPENAI_API_KEY'] = 'fallback-from-env'
resolved = c.resolve_api_key('openai')
print("resolve fallback:", repr(resolved))

# Check raw source
src = open(r'F:\AI data\codex\mmi\mmi\core\config.py', encoding='utf-8').read()
idx = src.find('def mask_api_key')
end = src.find('\ndef ', idx+1)
print()
print("=== Raw source of mask_api_key ===")
print(src[idx:end])