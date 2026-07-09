"""TypeScript AST helpers for eval graders, backed by tree-sitter-typescript.

Graders use these structural queries instead of regexes so a check reflects
the code's parse tree -- function boundaries, async-ness, call targets,
returned-value shapes, discriminated unions -- rather than surface text.
tree-sitter parsing is error-tolerant, so partial or slightly malformed
model output still yields a usable tree.
"""

from __future__ import annotations

import functools
from typing import Iterator, NamedTuple

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

# Node types that introduce a callable in the tree-sitter-typescript grammar.
_FUNCTION_TYPES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function",  # `const f = function () {}`
        "arrow_function",
        "method_definition",
    }
)

# I/O the pure core must not perform, each mapped to the token reported in
# failure messages. Member access (`db.x`), the `process.env` read, and the
# specific nondeterministic calls are matched structurally, not by substring.
_IO_MEMBER_OBJECTS = {"db": "db.", "emailService": "emailService.", "console": "console."}


@functools.cache
def _parser() -> Parser:
    return Parser(Language(tree_sitter_typescript.language_typescript()))


def parse(code: str) -> Node:
    """Parse TypeScript source and return the tree's root node."""
    return _parser().parse(code.encode("utf-8")).root_node


def node_text(node: Node) -> str:
    """The source text a node spans."""
    return node.text.decode("utf-8")


def first_line(node: Node) -> str:
    """The first source line a node spans (for failure snippets)."""
    return node_text(node).splitlines()[0] if node_text(node) else ""


def walk(node: Node) -> Iterator[Node]:
    """Yield every node in the subtree in pre-order."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


class Function(NamedTuple):
    """A callable found in the tree."""

    name: str | None
    is_async: bool
    node: Node


def _function_name(node: Node) -> str | None:
    """The declared name of a function, or None if anonymous.

    Declarations and methods carry a `name` field directly; arrow and
    function expressions take their name from the binding they are assigned
    to (a `const`/`let` declarator or an object property).
    """
    named = node.child_by_field_name("name")
    if named is not None:
        return node_text(named)
    parent = node.parent
    if parent is not None and parent.type == "variable_declarator":
        binding = parent.child_by_field_name("name")
        if binding is not None:
            return node_text(binding)
    if parent is not None and parent.type == "pair":
        key = parent.child_by_field_name("key")
        if key is not None:
            return node_text(key)
    return None


def _is_async(node: Node) -> bool:
    return any(child.type == "async" for child in node.children)


def functions(code: str) -> list[Function]:
    """Every callable in `code`, including anonymous and nested ones."""
    return [
        Function(_function_name(n), _is_async(n), n)
        for n in walk(parse(code))
        if n.type in _FUNCTION_TYPES
    ]


def named_functions(code: str) -> list[Function]:
    """Callables that have a resolvable name."""
    return [fn for fn in functions(code) if fn.name is not None]


class Binding(NamedTuple):
    """A named `const`/`let` variable that names a non-trivial expression."""

    name: str
    node: Node


# Initializer node types that compute or decide something. An explaining
# variable binds one of these to a name so the reader sees the concept
# instead of re-deriving it. Bare identifiers, member access, and literals
# are excluded (a pass-through names nothing new); function expressions are
# excluded too -- they are callables, already counted by `functions`.
_EXPLAINING_INIT_TYPES = frozenset(
    {
        "binary_expression",
        "unary_expression",
        "ternary_expression",
        "call_expression",
        "await_expression",
        "new_expression",
    }
)


def explaining_variables(code: str) -> list[Binding]:
    """Named `const`/`let` bindings whose initializer names a concept.

    An explaining variable turns an inline sub-expression -- a boolean
    condition, an arithmetic step, a call result -- into a named local, so
    the name documents intent the way an extracted function would. This is
    a first-class clarity move alongside extract-function, so a grader that
    scores intent (not one implementation) must see it. Trivial
    pass-throughs (`const name = user.name`), bare literals (`const x = 3`),
    and function expressions are excluded.
    """
    out: list[Binding] = []
    for n in walk(parse(code)):
        if n.type != "variable_declarator":
            continue
        name = n.child_by_field_name("name")
        value = n.child_by_field_name("value")
        if name is None or name.type != "identifier" or value is None:
            continue
        if value.type not in _EXPLAINING_INIT_TYPES:
            continue
        out.append(Binding(node_text(name), n))
    return out


def io_tokens(node: Node) -> list[str]:
    """I/O tokens performed anywhere in a node's subtree (order-preserved).

    Detects `await`, member access on `db`/`emailService`/`console`, the
    `process.env` read, and `fetch(` / `Date.now(` / `Math.random(` calls --
    the effects and nondeterminism a pure core must avoid.
    """
    found: list[str] = []
    for n in walk(node):
        if n.type == "await_expression":
            found.append("await")
        elif n.type == "member_expression":
            obj = n.child_by_field_name("object")
            prop = n.child_by_field_name("property")
            if obj is None or obj.type != "identifier":
                continue
            name = node_text(obj)
            prop_text = node_text(prop) if prop is not None else ""
            if name in _IO_MEMBER_OBJECTS:
                found.append(_IO_MEMBER_OBJECTS[name])
            elif name == "process" and prop_text == "env":
                found.append("process.env")
            elif name == "Date" and prop_text == "now":
                found.append("Date.now(")
            elif name == "Math" and prop_text == "random":
                found.append("Math.random(")
        elif n.type == "call_expression":
            callee = n.child_by_field_name("function")
            if callee is not None and callee.type == "identifier" and node_text(callee) == "fetch":
                found.append("fetch(")
    seen: set[str] = set()
    ordered: list[str] = []
    for token in found:
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def object_literals(node: Node) -> Iterator[Node]:
    """Yield every object-literal node in the subtree."""
    return (n for n in walk(node) if n.type == "object")


def object_keys(obj_node: Node) -> set[str]:
    """Property names declared directly in an object literal."""
    keys: set[str] = set()
    for child in obj_node.children:
        if child.type == "pair":
            key = child.child_by_field_name("key")
            if key is not None:
                keys.add(node_text(key).strip("\"'"))
        elif child.type == "shorthand_property_identifier":
            keys.add(node_text(child))
    return keys


def builds_object_with_keys(node: Node, required: set[str]) -> bool:
    """True if the subtree builds an object literal containing all `required` keys."""
    return any(required <= object_keys(obj) for obj in object_literals(node))


def has_kind_discriminant(code: str) -> bool:
    """True if a type or object literal uses a `kind` discriminant property.

    The `kind` tag is the discriminated-union idiom for returning a decision
    as data; a `property_identifier` named `kind` inside a type's
    `property_signature` or an object literal's `pair` marks it.
    """
    for n in walk(parse(code)):
        if (
            n.type == "property_identifier"
            and node_text(n) == "kind"
            and n.parent is not None
            and n.parent.type in ("property_signature", "pair")
        ):
            return True
    return False
