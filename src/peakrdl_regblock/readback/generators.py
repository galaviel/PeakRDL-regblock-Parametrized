from typing import TYPE_CHECKING, List

from systemrdl.node import RegNode

from ..forloop_generator import RDLForLoopGenerator, LoopBody

if TYPE_CHECKING:
    from ..exporter import RegblockExporter

from systemrdl.ast.references import ParameterRef  # galaviel

class ReadbackLoopBody(LoopBody):
    """
    galaviel this just adds the search & replace of each dim size.
    not sure why we need this - we know the dim's in advance.. not sure why we really need to count anything here.
    not really needed - I think - since we know #regs per DIM in advance .. don't really understand why we need this
    """
    def __init__(self, dim: int, iterator: str, i_type: str) -> None:
        super().__init__(dim, iterator, i_type)
        self.n_regs = 0     

    def __str__(self) -> str:
        # replace $i#sz token when stringifying
        s = super().__str__()
        token = f"${self.iterator}sz"
        s = s.replace(token, str(self.n_regs))
        return s

class ReadbackAssignmentGenerator(RDLForLoopGenerator):
    i_type = "genvar"
    loop_body_cls = ReadbackLoopBody

    def __init__(self, exp:'RegblockExporter') -> None:
        super().__init__()
        self.exp = exp

        # The readback array collects all possible readback values into a flat
        # array. The array width is equal to the CPUIF bus width. Each entry in
        # the array represents an aligned read access.
        self.global_offset_str  = ""        # galaviel offset of everything before and not including the current register we're in
        self.global_offset_arr  = []        # galaviel same as above only components (some int, some str). concat it to get the _str version above
        
        self.reg_offset_str     = ""        # e.g dim1*dim2*dim3
        
        self.array_size = ""                      # galaviel this is the over-all array size, use it in template..
        self.array_size_symbolic = False          # True if any of the regs' dim is a parameter
        
           
         
        self.start_offset_stack = [] # type: List[int]    # galaviel make this either int/str (str in case dim is ParameterRef/string name of the param)
        self.dim_stack = [] # type: List[int]

    @property
    def current_offset_str(self) -> str:
        """
        Derive a string that represents the current offset being assigned.
        This consists of:
        - The current integer offset
        - multiplied index of any enclosing loop

        The integer offset from "current_offset" is static and is monotonically
        incremented as more register assignments are processed.

        The component of the offset from loops is added by multiplying the current
        loop index by the loop size.
        Since the loop's size is not known at this time, it is emitted as a
        placeholder token like: $i0sz, $i1sz, $i2sz, etc
        These tokens can be replaced once the loop body has been completed and the
        size of its contents is known.
        """
        offset_parts = []
        #galaviel
        if False:
            for i in range(self._loop_level):
                offset_parts.append(f"i{i}*$i{i}sz")
            offset_parts.append(str(self.current_offset))
        else:
            
            # append global
            if len(self.global_offset_arr) != 0:
                offset_parts.extend(self.global_offset_arr)
                
            # append local (current) reg -- Array
            if self._loop_level != 0:
                for i in range(self._loop_level):
                    if i == 0:
                        offset_parts.append(f"i{i}"                     )       # galaviel TODO maybe need to reverse self.dim_stack() ? 
                    else:
                        offset_parts.append(f"i{i}*" + self.dim_stack[i])
                
        # consolidate
        out_str = self.consolidate_offset(offset_parts)
        return out_str

    def push_loop(self, dim: int) -> None:
        super().push_loop(dim)
        #galaviel self.start_offset_stack.append(self.current_offset)
        self.dim_stack.append(dim)

        # galaviel        
        if isinstance(dim, str):
            self.array_size_symbolic = True                     # if at least 1 DIM of 1 Reg is symbolic - the entire readback array size is symbolic
            
        # galaviel acc the offset inside the reg
        if self.reg_offset_str != "":
            self.reg_offset_str += "*"
        self.reg_offset_str += str(dim)
        

    def pop_loop(self) -> None:
        #galaviel start_offset = self.start_offset_stack.pop()
        dim = self.dim_stack.pop()

        # Number of registers enclosed in this loop
        # galaviel
        if isinstance(dim, str):        
            n_regs = dim
        else:
            # galaviel
            if True:
                n_regs = self.current_offset                    # make current_offset count only inside 1 loop (not accomulating)
            else:
                n_regs = self.current_offset - start_offset
        self.current_loop.n_regs = n_regs # type: ignore

        super().pop_loop()


    def enter_Reg(self, node: RegNode) -> None:
        if not node.has_sw_readable:
            return
        
        accesswidth = node.get_property('accesswidth')
        regwidth = node.get_property('regwidth')
        rbuf = node.get_property('buffer_reads')
        if rbuf:
            trigger = node.get_property('rbuffer_trigger')
            is_own_trigger = (isinstance(trigger, RegNode) and trigger == node)
            if is_own_trigger:
                if accesswidth < regwidth:
                    self.process_buffered_reg_with_bypass(node, regwidth, accesswidth)
                else:
                    # bypass cancels out. Behaves like a normal reg
                    self.process_reg(node)
            else:
                self.process_buffered_reg(node, regwidth, accesswidth)
        elif accesswidth < regwidth:
            self.process_wide_reg(node, accesswidth)
        else:
            self.process_reg(node)

    # galaviel - when exiting reg, add its total #regs (mult all its dimentions) to the global/total
    def exit_Reg(self, node: RegNode) -> None:
        
        # append local (current) reg -- Scalar
        if self._loop_level == 0 and node.has_sw_readable:
            self.reg_offset_str     = "1"   # galaviel if not an array, add 1 ...
        
        #offset_parts.append("1")
        
        if self.reg_offset_str != "":
            self.global_offset_arr.append(self.reg_offset_str)
        if self.global_offset_str != "":
            self.global_offset_str += "+"
        self.global_offset_str += self.reg_offset_str
        
        # galaviel consolidate global offset accomulated thus far
        # if it contains X + X then re-write that more nicely as 2*x
        self.global_offset_str = self.consolidate_offset(self.global_offset_arr)
        
        # galaviel reset
        self.reg_offset_str     = ""        # reset upon entry to each reg .. it's a pre-reg accomulator it's not global
        
        
    def consolidate_offset(self, arr_in):
        """
        galaviel consolidate global offset accomulated thus far
        if it contains X + X then re-write that more nicely as 2*x
        """
        from collections import Counter
        c = Counter(arr_in)
        str_out = ""
        for value, num_occur in c.items():
            if str_out != "":
                str_out += "+"
            if num_occur == 1:
                str_out += "%s"    % value
            elif value == "1":
                str_out += "%d"    % num_occur
            else:
                str_out += "%d*%s" % (num_occur, value)
        return str_out
            
            

    def process_reg(self, node: RegNode) -> None:
        current_bit = 0
        rd_strb = f"({self.exp.dereferencer.get_access_strobe(node)} && !decoded_req_is_wr)"
        # Fields are sorted by ascending low bit
        for field in node.fields():
            if not field.is_sw_readable:
                continue

            # insert reserved assignment before this field if needed
            if current_bit == 0 and (not isinstance(field.low, ParameterRef)):          # galaviel can't tell if this is needed in case field.low is symbolic.. it might be 0..
                if field.low != current_bit:                                            # TODO galaviel replace assign with blocking assignment, first assign entire reg to zero, only then over-ride existing fields. Same effect.
                    self.add_content(f"assign readback_array[{self.current_offset_str}][{field.low-1}:{current_bit}] = '0;")

            value = self.exp.dereferencer.get_value(field)
            
            if isinstance(field.msb, ParameterRef) or isinstance(field.lsb, ParameterRef):      # galaviel keep it simple.. for now..dont support bitswap (anyways can't tell if symbolic)
                pass            
            elif field.msb < field.lsb:
                # Field gets bitswapped since it is in [low:high] orientation
                value = f"{{<<{{{value}}}}}"
            
            if isinstance(field.high, ParameterRef):    # galaviel ugly .. need self.field_high_str .. 
                field_high = field.high.param.name
            else:
                field_high = field.high
            if isinstance(field.low, ParameterRef):    # galaviel ugly .. need self.field_low_str .. 
                field_low = field.low.param.name
            else:
                field_low = field.low
                
            self.add_content(f"assign readback_array[{self.current_offset_str}][{field_high}:{field_low}] = {rd_strb} ? {value} : '0;")

            if ( isinstance(field.high, ParameterRef)): # galaviel
                current_bit = field.high.param.name + "1"
            else:
                current_bit = field.high + 1

        # Insert final reserved assignment if needed
        bus_width = self.exp.cpuif.data_width
        if not isinstance(current_bit, str):        # galaviel one of the bit ranges is symbolic, we can't know if below is required.. so keep it simple: always assume all regs fit into teh bus width
            if current_bit < bus_width:
                self.add_content(f"assign readback_array[{self.current_offset_str}][{bus_width-1}:{current_bit}] = '0;")



    def process_buffered_reg(self, node: RegNode, regwidth: int, accesswidth: int) -> None:
        rbuf = self.exp.read_buffering.get_rbuf_data(node)

        if accesswidth < regwidth:
            # Is wide reg
            n_subwords = regwidth // accesswidth
            astrb = self.exp.dereferencer.get_access_strobe(node, reduce_substrobes=False)
            for i in range(n_subwords):
                rd_strb = f"({astrb}[{i}] && !decoded_req_is_wr)"
                bslice = f"[{(i + 1) * accesswidth - 1}:{i*accesswidth}]"
                self.add_content(f"assign readback_array[{self.current_offset_str}] = {rd_strb} ? {rbuf}{bslice} : '0;")
                self.current_offset += 1

        else:
            # Is regular reg
            rd_strb = f"({self.exp.dereferencer.get_access_strobe(node)} && !decoded_req_is_wr)"
            self.add_content(f"assign readback_array[{self.current_offset_str}][{regwidth-1}:0] = {rd_strb} ? {rbuf} : '0;")

            bus_width = self.exp.cpuif.data_width
            if regwidth < bus_width:
                self.add_content(f"assign readback_array[{self.current_offset_str}][{bus_width-1}:{regwidth}] = '0;")

            self.current_offset += 1


    def process_buffered_reg_with_bypass(self, node: RegNode, regwidth: int, accesswidth: int) -> None:
        """
        Special case for a buffered register when the register is its own trigger.
        First sub-word shall bypass the read buffer and assign directly.
        Subsequent subwords assign from the buffer.
        Caller guarantees this is a wide reg
        """
        astrb = self.exp.dereferencer.get_access_strobe(node, reduce_substrobes=False)

        # Generate assignments for first sub-word
        bidx = 0
        rd_strb = f"({astrb}[0] && !decoded_req_is_wr)"
        for field in node.fields():
            if not field.is_sw_readable:
                continue

            if field.low >= accesswidth:
                # field is not in this subword.
                break

            if bidx < field.low:
                # insert padding before
                self.add_content(f"assign readback_array[{self.current_offset_str}][{field.low - 1}:{bidx}] = '0;")

            if field.high >= accesswidth:
                # field gets truncated
                r_low = field.low
                r_high = accesswidth - 1
                f_low = 0
                f_high = accesswidth - 1 - field.low

                if field.msb < field.lsb:
                    # Field gets bitswapped since it is in [low:high] orientation
                    # Mirror the low/high indexes
                    f_low = field.width - 1 - f_low
                    f_high = field.width - 1 - f_high
                    f_low, f_high = f_high, f_low
                    value = f"{{<<{{{self.exp.dereferencer.get_value(field)}[{f_high}:{f_low}]}}}}"
                else:
                    value = self.exp.dereferencer.get_value(field) + f"[{f_high}:{f_low}]"

                self.add_content(f"assign readback_array[{self.current_offset_str}][{r_high}:{r_low}] = {rd_strb} ? {value} : '0;")
                bidx = accesswidth
            else:
                # field fits in subword
                value = self.exp.dereferencer.get_value(field)
                if field.msb < field.lsb:
                    # Field gets bitswapped since it is in [low:high] orientation
                    value = f"{{<<{{{value}}}}}"
                self.add_content(f"assign readback_array[{self.current_offset_str}][{field.high}:{field.low}] = {rd_strb} ? {value} : '0;")
                bidx = field.high + 1

        # pad up remainder of subword
        if bidx < accesswidth:
            self.add_content(f"assign readback_array[{self.current_offset_str}][{accesswidth-1}:{bidx}] = '0;")
        self.current_offset += 1

        # Assign remainder of subwords from read buffer
        n_subwords = regwidth // accesswidth
        rbuf = self.exp.read_buffering.get_rbuf_data(node)
        for i in range(1, n_subwords):
            rd_strb = f"({astrb}[{i}] && !decoded_req_is_wr)"
            bslice = f"[{(i + 1) * accesswidth - 1}:{i*accesswidth}]"
            self.add_content(f"assign readback_array[{self.current_offset_str}] = {rd_strb} ? {rbuf}{bslice} : '0;")
            self.current_offset += 1

    def process_wide_reg(self, node: RegNode, accesswidth: int) -> None:
        bus_width = self.exp.cpuif.data_width

        subword_idx = 0
        current_bit = 0 # Bit-offset within the wide register
        access_strb = self.exp.dereferencer.get_access_strobe(node, reduce_substrobes=False)
        # Fields are sorted by ascending low bit
        for field in node.fields():
            if not field.is_sw_readable:
                continue

            # insert zero assignment before this field if needed
            if field.low >= accesswidth*(subword_idx+1):
                # field does not start in this subword
                if current_bit > accesswidth * subword_idx:
                    # current subword had content. Assign remainder
                    low = current_bit % accesswidth
                    high = bus_width - 1
                    self.add_content(f"assign readback_array[{self.current_offset_str}][{high}:{low}] = '0;")
                    self.current_offset += 1

                # Advance to subword that contains the start of the field
                subword_idx = field.low // accesswidth
                current_bit = accesswidth * subword_idx

            if current_bit != field.low:
                # assign zero up to start of this field
                low = current_bit % accesswidth
                high = (field.low % accesswidth) - 1
                self.add_content(f"assign readback_array[{self.current_offset_str}][{high}:{low}] = '0;")
                current_bit = field.low


            # Assign field
            # loop until the entire field's assignments have been generated
            field_pos = field.low
            while current_bit <= field.high:
                # Assign the field
                rd_strb = f"({access_strb}[{subword_idx}] && !decoded_req_is_wr)"
                if (field_pos == field.low) and (field.high < accesswidth*(subword_idx+1)):
                    # entire field fits into this subword
                    low = field.low - accesswidth * subword_idx
                    high = field.high - accesswidth * subword_idx

                    value = self.exp.dereferencer.get_value(field)
                    if field.msb < field.lsb:
                        # Field gets bitswapped since it is in [low:high] orientation
                        value = f"{{<<{{{value}}}}}"

                    self.add_content(f"assign readback_array[{self.current_offset_str}][{high}:{low}] = {rd_strb} ? {value} : '0;")

                    current_bit = field.high + 1

                    if current_bit == accesswidth*(subword_idx+1):
                        # Field ends at the subword boundary
                        subword_idx += 1
                        self.current_offset += 1
                elif field.high >= accesswidth*(subword_idx+1):
                    # only a subset of the field can fit into this subword
                    # high end gets truncated

                    # assignment slice
                    r_low = field_pos - accesswidth * subword_idx
                    r_high = accesswidth - 1

                    # field slice
                    f_low = field_pos - field.low
                    f_high = accesswidth * (subword_idx + 1) - 1 - field.low

                    if field.msb < field.lsb:
                        # Field gets bitswapped since it is in [low:high] orientation
                        # Mirror the low/high indexes
                        f_low = field.width - 1 - f_low
                        f_high = field.width - 1 - f_high
                        f_low, f_high = f_high, f_low

                        value = f"{{<<{{{self.exp.dereferencer.get_value(field)}[{f_high}:{f_low}]}}}}"
                    else:
                        value = self.exp.dereferencer.get_value(field) + f"[{f_high}:{f_low}]"

                    self.add_content(f"assign readback_array[{self.current_offset_str}][{r_high}:{r_low}] = {rd_strb} ? {value} : '0;")

                    # advance to the next subword
                    subword_idx += 1
                    current_bit = accesswidth * subword_idx
                    field_pos = current_bit
                    self.current_offset += 1
                else:
                    # only a subset of the field can fit into this subword
                    # finish field

                    # assignment slice
                    r_low = field_pos - accesswidth * subword_idx
                    r_high = field.high - accesswidth * subword_idx

                    # field slice
                    f_low = field_pos - field.low
                    f_high = field.high - field.low

                    if field.msb < field.lsb:
                        # Field gets bitswapped since it is in [low:high] orientation
                        # Mirror the low/high indexes
                        f_low = field.width - 1 - f_low
                        f_high = field.width - 1 - f_high
                        f_low, f_high = f_high, f_low

                        value = f"{{<<{{{self.exp.dereferencer.get_value(field)}[{f_high}:{f_low}]}}}}"
                    else:
                        value = self.exp.dereferencer.get_value(field) + f"[{f_high}:{f_low}]"

                    self.add_content(f"assign readback_array[{self.current_offset_str}][{r_high}:{r_low}] = {rd_strb} ? {value} : '0;")

                    current_bit = field.high + 1
                    if current_bit == accesswidth*(subword_idx+1):
                        # Field ends at the subword boundary
                        subword_idx += 1
                        self.current_offset += 1

        # insert zero assignment after the last field if needed
        if current_bit > accesswidth * subword_idx:
            # current subword had content. Assign remainder
            low = current_bit % accesswidth
            high = bus_width - 1
            self.add_content(f"assign readback_array[{self.current_offset_str}][{high}:{low}] = '0;")
            self.current_offset += 1
