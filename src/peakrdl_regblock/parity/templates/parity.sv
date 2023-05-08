{% if parity_assignments is not none %}
always_comb begin
	parity_error = 1'b0;
	{{parity_assignments|indent}}
end
{%- endif %}