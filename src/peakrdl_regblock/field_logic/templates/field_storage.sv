{%- import 'field_logic/templates/counter_macros.sv' as counter_macros with context -%}
// Field: {{node.get_path()}}
always_comb begin
	automatic logic [{{field_logic.get_storage_msbit(node)}}:0] next_c = {{field_logic.get_storage_identifier(node)}};
    automatic logic load_next_c = '0;
    {%- for signal in extra_combo_signals %}
    {{field_logic.get_field_combo_identifier(node, signal.name)}} = {{signal.default_assignment}};
    {%- endfor %}
    {% for conditional in conditionals %}
    {%- if not loop.first %} else {% endif %}if({{conditional.get_predicate(node)}}) begin // {{conditional.comment}}
        {%- for assignment in conditional.get_assignments(node) %}
        {{assignment|indent}}
        {%- endfor %}
    end
    {%- endfor %}
    {%- if node.is_up_counter %}
    {{counter_macros.up_counter(node)}}
    {%- endif %}
    {%- if node.is_down_counter %}
    {{counter_macros.down_counter(node)}}
    {%- endif %}
    {{field_logic.get_field_combo_identifier(node, "next")}} = next_c;
    {{field_logic.get_field_combo_identifier(node, "load_next")}} = load_next_c;
    {%- if node.implements_parity %}
    {{field_logic.get_field_parity_combo_identifier(node, "parity_error")}} = ({{field_logic.get_parity_storage_identifier(node)}} != ^{{field_logic.get_storage_identifier(node)}}};
    {%- endif %}
end
always_ff {{get_always_ff_event(resetsignal)}} begin
    {% if reset is not none -%}
    if({{get_resetsignal(resetsignal)}}) begin
        {{field_logic.get_storage_identifier(node)}} <= {{reset}};
    end else {% endif %}if({{field_logic.get_field_combo_identifier(node, "load_next")}}) begin
        {{field_logic.get_storage_identifier(node)}} <= {{field_logic.get_field_combo_identifier(node, "next")}};
    end
    {%- if field_logic.has_next_q(node) %}
    {{field_logic.get_next_q_identifier(node)}} <= {{get_input_identifier(node)}};
    {%- endif %}
end

{%- if node.implements_parity %}
always_ff {{get_always_ff_event(resetsignal)}} begin
    {% if reset is not none -%}
    if({{get_resetsignal(resetsignal)}}) begin
        {{field_logic.get_parity_storage_identifier(node)}} <= ^{{reset}};
    end else {% endif %}if({{field_logic.get_field_combo_identifier(node, "load_next")}}) begin
        {{field_logic.get_parity_storage_identifier(node)}} <= ^{{field_logic.get_field_combo_identifier(node, "next")}};
    end
    {%- if field_logic.has_next_q(node) %}
    {{field_logic.get_next_q_identifier(node)}} <= {{get_input_identifier(node)}};
    {%- endif %}
end
{%- endif %}
