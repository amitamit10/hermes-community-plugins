"""Benchmark-only helper: load a built GOAT bundle and call its registered tools
exactly as Hermes would (JSON handler path). Does NOT touch production code."""
import importlib.util, json, sys, time, uuid
from pathlib import Path

def load_tools(bundle):
    d = Path(bundle); pkg = "goatbundle_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(pkg, d/"__init__.py", submodule_search_locations=[str(d)])
    mod = importlib.util.module_from_spec(spec); sys.modules[pkg] = mod; spec.loader.exec_module(mod)
    class Ctx:
        tools = {}
        def register_tool(self, name, toolset, schema, handler, description): self.tools[name] = handler
    ctx = Ctx(); mod.register(ctx)
    return ctx.tools

def call(tools, name, args):
    t = time.perf_counter()
    raw = tools[name](args)
    ms = (time.perf_counter() - t) * 1000
    try: out = json.loads(raw)
    except Exception: out = {"ok": False, "error": {"code": "NONJSON"}, "raw": raw[:200]}
    return out, ms
