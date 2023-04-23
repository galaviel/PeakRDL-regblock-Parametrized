from typing import TYPE_CHECKING, Optional, List, Union
import textwrap

from systemrdl.walker import RDLListener, RDLWalker

if TYPE_CHECKING:
    from systemrdl.node import AddressableNode, Node

class Body:

    def __init__(self) -> None:
        self.children = [] # type: List[Union[str, Body]]

    def __str__(self) -> str:
        s = '\n'.join((str(x) for x in self.children))
        return s


class LoopBody(Body):
    """
    galaviel - this class has a bad name - it's not really the "loopBody" rather the entire loop.
    the 'Body' class is the content of the assignmetns (not including the for(..) line
    This class adds the 'for()' line to that.. very confusing.
    """
    def __init__(self, dim: int, iterator: str, i_type: str) -> None:
        super().__init__()
        self.dim = dim
        self.iterator = iterator
        self.i_type = i_type

    def __str__(self) -> str:
        s = super().__str__()
        return (
            f"for({self.i_type} {self.iterator}=0; {self.iterator}<{self.dim}; {self.iterator}++) begin\n"
            + textwrap.indent(s, "    ")
            + "\nend"
        )


class ForLoopGenerator:
    i_type = "int"
    loop_body_cls = LoopBody

    def __init__(self) -> None:
        self._loop_level = 0
        self._stack = [] # type: List[Body]

    @property
    def current_loop(self) -> Body:
        return self._stack[-1]

    def push_loop(self, dim: int) -> None:
        i = f"i{self._loop_level}"
        b = self.loop_body_cls(dim, i, self.i_type)
        self._stack.append(b)
        self._loop_level += 1

    def add_content(self, s: str) -> None:
        """
        galaviel content == loop body
        'content' seems to be the verilog assignments that are executed in the loop
        note that it seems, reading the code here, in a mutli-level loop, each loop level can have 'content in addition to
        sub-loops. 
        """
        self.current_loop.children.append(s)

    def pop_loop(self) -> None:
        b = self._stack.pop()

        if b.children:
            # Loop body is not empty. Attach it to the parent
            self.current_loop.children.append(b)
        self._loop_level -= 1

    def start(self) -> None:
        assert not self._stack
        b = Body()
        self._stack.append(b)

    def finish(self) -> Optional[str]:
        b = self._stack.pop()
        assert not self._stack

        if not b.children:
            return None
        return str(b)

class RDLForLoopGenerator(ForLoopGenerator, RDLListener):

    def get_content(self, node: 'Node') -> Optional[str]:
        self.start()
        walker = RDLWalker()
        walker.walk(node, self, skip_top=True)
        return self.finish()

    def enter_AddressableComponent(self, node: 'AddressableNode') -> None:
        if not node.is_array:
            return

        for dim in node.array_dimensions:
            # galaviel
            from systemrdl.ast.references import ParameterRef  # galaviel
            if isinstance(dim, ParameterRef):
                self.push_loop(dim.param.name)
            else:
                self.push_loop(dim)

    def exit_AddressableComponent(self, node: 'AddressableNode') -> None:
        if not node.is_array:
            return

        for _ in node.array_dimensions:
            self.pop_loop()
            
        
        
