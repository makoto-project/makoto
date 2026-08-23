"""Bounded, non-backtracking evaluator for the Makoto v0.2 pattern vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MAX_PATTERN_STATES = 131_072
_OUTSIDE_META = frozenset(".^$*+?{}[]()|\\")
_ESCAPES = {
    "\\": "\\",
    ".": ".",
    "^": "^",
    "$": "$",
    "*": "*",
    "+": "+",
    "?": "?",
    "{": "{",
    "}": "}",
    "[": "[",
    "]": "]",
    "(": "(",
    ")": ")",
    "|": "|",
    "-": "-",
    "t": "\t",
    "n": "\n",
    "r": "\r",
}


class PatternError(ValueError):
    """Raised when a decoded makotoPattern is syntactically unsupported."""


class PatternLimitError(PatternError):
    """Raised before compilation when a pattern exceeds a bounded limit."""


@dataclass(frozen=True)
class LiteralNode:
    value: str


@dataclass(frozen=True)
class DotNode:
    pass


@dataclass(frozen=True)
class AnchorNode:
    kind: Literal["begin", "end"]


@dataclass(frozen=True)
class ClassNode:
    values: frozenset[str]
    ranges: tuple[tuple[int, int], ...]
    negated: bool


@dataclass(frozen=True)
class ConcatNode:
    children: tuple[Node, ...]


@dataclass(frozen=True)
class AlternateNode:
    children: tuple[Node, ...]


@dataclass(frozen=True)
class RepeatNode:
    child: Node
    minimum: int
    maximum: int | None
    copy_for_unbounded: bool = False


Node = LiteralNode | DotNode | AnchorNode | ClassNode | ConcatNode | AlternateNode | RepeatNode


def _is_control(value: str) -> bool:
    code_point = ord(value)
    return code_point <= 0x1F or 0x7F <= code_point <= 0x9F


def _contains_repeat(node: Node) -> bool:
    if isinstance(node, RepeatNode):
        return True
    if isinstance(node, (ConcatNode, AlternateNode)):
        return any(_contains_repeat(child) for child in node.children)
    return False


class _Parser:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.index = 0

    def parse(self) -> Node:
        if not self.pattern:
            raise PatternError("pattern is empty")
        node = self._alternation(root=True, terminator=None)
        if self.index != len(self.pattern):
            raise PatternError(f"unexpected token {self.pattern[self.index]!r}")
        return node

    def _alternation(self, *, root: bool, terminator: str | None) -> Node:
        alternatives = [self._alternative(root=root, terminator=terminator)]
        while self._peek() == "|":
            self.index += 1
            alternatives.append(self._alternative(root=root, terminator=terminator))
        if len(alternatives) == 1:
            return alternatives[0]
        return AlternateNode(tuple(alternatives))

    def _alternative(self, *, root: bool, terminator: str | None) -> Node:
        children: list[Node] = []
        while self.index < len(self.pattern):
            current = self._peek()
            if current == "|" or (terminator is not None and current == terminator):
                break
            child = self._quantified(root=root)
            children.append(child)
        if not children:
            raise PatternError("empty alternative or group")
        for position, child in enumerate(children):
            if isinstance(child, AnchorNode):
                if not root:
                    raise PatternError("anchors are permitted only at root alternatives")
                if child.kind == "begin" and position != 0:
                    raise PatternError("begin anchor must be the first root atom")
                if child.kind == "end" and position != len(children) - 1:
                    raise PatternError("end anchor must be the last root atom")
        if len(children) == 1:
            return children[0]
        return ConcatNode(tuple(children))

    def _quantified(self, *, root: bool) -> Node:
        atom = self._atom(root=root)
        current = self._peek()
        if current not in {"?", "*", "+", "{"}:
            return atom
        if isinstance(atom, AnchorNode):
            raise PatternError("anchors cannot be quantified")
        if _contains_repeat(atom):
            raise PatternError("nested quantifiers are prohibited")
        minimum, maximum, copy_for_unbounded = self._quantifier()
        if self._peek() in {"?", "*", "+", "{"}:
            raise PatternError("nested or nongreedy quantifier is prohibited")
        return RepeatNode(atom, minimum, maximum, copy_for_unbounded)

    def _atom(self, *, root: bool) -> Node:
        del root
        current = self._peek()
        if current is None:
            raise PatternError("expected an atom")
        if current == ".":
            self.index += 1
            return DotNode()
        if current == "^":
            self.index += 1
            return AnchorNode("begin")
        if current == "$":
            self.index += 1
            return AnchorNode("end")
        if current == "(":
            self.index += 1
            child = self._alternation(root=False, terminator=")")
            if self._peek() != ")":
                raise PatternError("group is not closed")
            self.index += 1
            return child
        if current == "[":
            return self._character_class()
        if current == "\\":
            value, _ = self._escaped(in_class=False)
            return LiteralNode(value)
        if current in _OUTSIDE_META:
            raise PatternError(f"unescaped metacharacter {current!r}")
        if _is_control(current):
            raise PatternError("control scalar is prohibited in pattern syntax")
        self.index += 1
        return LiteralNode(current)

    def _character_class(self) -> Node:
        self.index += 1
        negated = self._peek() == "^"
        if negated:
            self.index += 1
        tokens: list[tuple[str, bool]] = []
        while True:
            current = self._peek()
            if current is None:
                raise PatternError("character class is not closed")
            if current == "]":
                self.index += 1
                break
            if current == "\\":
                tokens.append(self._escaped(in_class=True))
                continue
            if current == "-":
                tokens.append((current, False))
                self.index += 1
                continue
            if _is_control(current):
                raise PatternError("control scalar is prohibited in character class")
            tokens.append((current, False))
            self.index += 1
        if not tokens:
            raise PatternError("character class is empty")

        values: set[str] = set()
        ranges: list[tuple[int, int]] = []
        position = 0
        while position < len(tokens):
            value, escaped = tokens[position]
            if value == "-" and not escaped:
                raise PatternError("dangling or chained class range")
            if position + 1 < len(tokens) and tokens[position + 1] == ("-", False):
                if position + 2 >= len(tokens):
                    raise PatternError("dangling class range")
                end, end_escaped = tokens[position + 2]
                if escaped or end_escaped or ord(value) > 0x7F or ord(end) > 0x7F:
                    raise PatternError("class ranges require unescaped ASCII endpoints")
                if ord(value) > ord(end):
                    raise PatternError("class range endpoints are reversed")
                ranges.append((ord(value), ord(end)))
                position += 3
                continue
            values.add(value)
            position += 1
        return ClassNode(frozenset(values), tuple(ranges), negated)

    def _escaped(self, *, in_class: bool) -> tuple[str, bool]:
        self.index += 1
        current = self._peek()
        if current is None or current not in _ESCAPES:
            raise PatternError("unsupported escape")
        if current == "-" and not in_class:
            raise PatternError("escaped hyphen is valid only inside a class")
        self.index += 1
        return _ESCAPES[current], True

    def _quantifier(self) -> tuple[int, int | None, bool]:
        current = self._peek()
        if current == "?":
            self.index += 1
            return 0, 1, False
        if current == "*":
            self.index += 1
            return 0, None, False
        if current == "+":
            self.index += 1
            return 1, None, False
        self.index += 1
        minimum = self._decimal()
        if self._peek() == "}":
            self.index += 1
            return minimum, minimum, False
        if self._peek() != ",":
            raise PatternError("invalid bounded quantifier")
        self.index += 1
        if self._peek() == "}":
            self.index += 1
            return minimum, None, True
        maximum = self._decimal()
        if self._peek() != "}":
            raise PatternError("bounded quantifier is not closed")
        self.index += 1
        if maximum < minimum:
            raise PatternError("bounded quantifier maximum is smaller than minimum")
        return minimum, maximum, False

    def _decimal(self) -> int:
        start = self.index
        while (current := self._peek()) is not None and current.isascii() and current.isdigit():
            self.index += 1
        value = self.pattern[start : self.index]
        if not value or (len(value) > 1 and value.startswith("0")):
            raise PatternError("quantifier bounds require canonical decimal integers")
        parsed = int(value)
        if parsed > 1000:
            raise PatternError("quantifier bound exceeds 1000")
        return parsed

    def _peek(self) -> str | None:
        return self.pattern[self.index] if self.index < len(self.pattern) else None


def parse_pattern(pattern: str, *, max_length: int = 4096) -> Node:
    if len(pattern) > max_length:
        raise PatternLimitError("pattern exceeds maxRegexLength")
    return _Parser(pattern).parse()


def _state_count(node: Node) -> int:
    if isinstance(node, (LiteralNode, DotNode, AnchorNode, ClassNode)):
        return 1
    if isinstance(node, ConcatNode):
        return sum(_state_count(child) for child in node.children)
    if isinstance(node, AlternateNode):
        return sum(_state_count(child) for child in node.children) + len(node.children) - 1
    if isinstance(node, RepeatNode):
        child_count = _state_count(node.child)
        if node.maximum == node.minimum:
            return node.minimum * child_count
        if node.maximum is None:
            if not node.copy_for_unbounded:
                return child_count + 1
            return (node.minimum + 1) * child_count + 1
        optional_copies = node.maximum - node.minimum
        return node.minimum * child_count + optional_copies * (child_count + 1)
    raise AssertionError("unreachable pattern node")


@dataclass
class _State:
    kind: Literal["literal", "dot", "class", "begin", "end", "split", "match"]
    value: object = None
    out: int | None = None
    out1: int | None = None


@dataclass
class _Fragment:
    start: int | None
    outs: list[tuple[int, Literal["out", "out1"]]]


@dataclass(frozen=True)
class CompiledPattern:
    pattern: str
    states: tuple[_State, ...]
    start: int

    @property
    def state_count(self) -> int:
        return len(self.states)

    def search(self, value: str, *, max_operations: int = 10_000_000) -> bool:
        active: set[int] = set()
        matched = False
        operations = 0

        def add_state(target: set[int], index: int | None, position: int) -> None:
            nonlocal operations, matched
            pending = [] if index is None else [index]
            visited: set[int] = set()
            while pending:
                state_index = min(pending)
                pending.remove(state_index)
                if state_index in visited:
                    continue
                visited.add(state_index)
                operations += 1
                if operations > max_operations:
                    raise PatternLimitError("pattern evaluation exceeded maxSchemaOperations")
                state = self.states[state_index]
                if state.kind == "split":
                    if state.out is not None:
                        pending.append(state.out)
                    if state.out1 is not None:
                        pending.append(state.out1)
                elif state.kind == "begin":
                    if position == 0 and state.out is not None:
                        pending.append(state.out)
                elif state.kind == "end":
                    if position == len(value) and state.out is not None:
                        pending.append(state.out)
                elif state.kind == "match":
                    matched = True
                else:
                    target.add(state_index)

        for position in range(len(value) + 1):
            add_state(active, self.start, position)
            if position == len(value):
                break
            following: set[int] = set()
            character = value[position]
            for state_index in sorted(active):
                state = self.states[state_index]
                accepted = False
                if state.kind == "literal":
                    accepted = character == state.value
                elif state.kind == "dot":
                    accepted = character not in {"\n", "\r"}
                elif state.kind == "class":
                    node = state.value
                    assert isinstance(node, ClassNode)
                    member = character in node.values or any(
                        lower <= ord(character) <= upper for lower, upper in node.ranges
                    )
                    accepted = not member if node.negated else member
                if accepted:
                    add_state(following, state.out, position + 1)
            active = following
        return matched


class _Compiler:
    def __init__(self) -> None:
        self.states: list[_State] = []

    def compile(self, node: Node) -> tuple[tuple[_State, ...], int]:
        fragment = self._node(node)
        match = self._add(_State("match"))
        if fragment.start is None:
            start = match
        else:
            start = fragment.start
            self._patch(fragment.outs, match)
        return tuple(self.states), start

    def _node(self, node: Node) -> _Fragment:
        if isinstance(node, LiteralNode):
            index = self._add(_State("literal", node.value))
            return _Fragment(index, [(index, "out")])
        if isinstance(node, DotNode):
            index = self._add(_State("dot"))
            return _Fragment(index, [(index, "out")])
        if isinstance(node, AnchorNode):
            index = self._add(_State(node.kind))
            return _Fragment(index, [(index, "out")])
        if isinstance(node, ClassNode):
            index = self._add(_State("class", node))
            return _Fragment(index, [(index, "out")])
        if isinstance(node, ConcatNode):
            result = _Fragment(None, [])
            for child in node.children:
                result = self._concat(result, self._node(child))
            return result
        if isinstance(node, AlternateNode):
            fragments = [self._node(child) for child in node.children]
            result = fragments[-1]
            for fragment in reversed(fragments[:-1]):
                split = self._add(_State("split", out=fragment.start, out1=result.start))
                result = _Fragment(split, fragment.outs + result.outs)
            return result
        if isinstance(node, RepeatNode):
            return self._repeat(node)
        raise AssertionError("unreachable pattern node")

    def _repeat(self, node: RepeatNode) -> _Fragment:
        if node.maximum is None and not node.copy_for_unbounded:
            child = self._node(node.child)
            split = self._add(_State("split", out=child.start))
            self._patch(child.outs, split)
            if node.minimum == 0:
                return _Fragment(split, [(split, "out1")])
            return _Fragment(child.start, [(split, "out1")])
        result = _Fragment(None, [])
        for _ in range(node.minimum):
            result = self._concat(result, self._node(node.child))
        if node.maximum == node.minimum:
            return result
        if node.maximum is None:
            child = self._node(node.child)
            split = self._add(_State("split", out=child.start))
            self._patch(child.outs, split)
            star = _Fragment(split, [(split, "out1")])
            return self._concat(result, star)
        for _ in range(node.maximum - node.minimum):
            child = self._node(node.child)
            split = self._add(_State("split", out=child.start))
            result = self._concat(result, _Fragment(split, child.outs + [(split, "out1")]))
        return result

    def _concat(self, left: _Fragment, right: _Fragment) -> _Fragment:
        if left.start is None:
            return right
        if right.start is None:
            return left
        self._patch(left.outs, right.start)
        return _Fragment(left.start, right.outs)

    def _patch(self, outs: list[tuple[int, Literal["out", "out1"]]], target: int) -> None:
        for index, field in outs:
            setattr(self.states[index], field, target)

    def _add(self, state: _State) -> int:
        self.states.append(state)
        return len(self.states) - 1


def compile_pattern(
    pattern: str,
    *,
    max_length: int = 4096,
    max_states: int = MAX_PATTERN_STATES,
) -> CompiledPattern:
    node = parse_pattern(pattern, max_length=max_length)
    state_count = _state_count(node) + 1
    if state_count > max_states:
        raise PatternLimitError(f"pattern compiles to {state_count} states; limit is {max_states}")
    states, start = _Compiler().compile(node)
    if len(states) != state_count:
        raise AssertionError(
            f"pattern state-count invariant failed: {len(states)} != {state_count}"
        )
    return CompiledPattern(pattern, states, start)
