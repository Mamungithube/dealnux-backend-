import ast

try:
    with open(r'c:\mamun file\Project File\dealnux-backend-\store\models.py') as f:
        code = f.read()
        ast.parse(code)
    print("✓ Syntax OK")
except SyntaxError as e:
    print(f"✗ Syntax Error at line {e.lineno}: {e.msg}")
    if e.text:
        print(f"   {e.text.strip()}")
    print(f"   Offset: {e.offset}")
