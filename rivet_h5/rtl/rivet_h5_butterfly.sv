module rivet_h5_butterfly (
    input wire clk, rst_n,
    input wire b_valid,
    output wire b_ready,
    input wire b_inverse,
    input wire [22:0] b_u, b_v, b_zeta,
    output wire b_m_valid,
    input wire b_m_ready,
    output wire [22:0] b_a, b_b
);
    localparam [23:0] Q = 24'd8380417;
    reg [1:0] state;
    reg inverse;
    reg [22:0] u, v, zeta, parallel_sum, out_a, out_b;
    wire [23:0] sum_uv = {1'b0,u} + {1'b0,v};
    wire [23:0] diff_uv = (u >= v) ?
        {1'b0,u} - {1'b0,v} : {1'b0,u} + Q - {1'b0,v};
    wire [23:0] canonical_sum = (sum_uv >= Q) ? sum_uv - Q : sum_uv;
    wire mont_ready, mont_valid;
    wire [22:0] mont_result;
    wire [23:0] sum_um = {1'b0,u} + {1'b0,mont_result};
    wire [23:0] reduced_um = (sum_um >= Q) ? sum_um - Q : sum_um;
    wire [23:0] diff_um = (u >= mont_result) ?
        {1'b0,u} - {1'b0,mont_result} :
        {1'b0,u} + Q - {1'b0,mont_result};
    assign b_ready = rst_n && (state == 0);
    assign b_m_valid = rst_n && (state == 3);
    assign b_a = b_m_valid ? out_a : 23'd0;
    assign b_b = b_m_valid ? out_b : 23'd0;
    rivet_h5_montgomery u_montgomery (
        .clk(clk), .rst_n(rst_n),
        .a_valid(rst_n && (state == 1)), .a_ready(mont_ready),
        .a(inverse ? diff_uv[22:0] : v), .b(zeta),
        .m_valid(mont_valid), .m_ready(rst_n && (state == 2)),
        .m(mont_result)
    );
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 0; inverse <= 0; u <= 0; v <= 0; zeta <= 0;
            parallel_sum <= 0; out_a <= 0; out_b <= 0;
        end else begin
            case (state)
                0: if (b_valid && b_ready) begin
                    u <= b_u; v <= b_v; zeta <= b_zeta;
                    inverse <= b_inverse; state <= 1;
                end
                1: if (mont_ready) begin
                    parallel_sum <= canonical_sum[22:0]; state <= 2;
                end
                2: if (mont_valid) begin
                    if (inverse) begin
                        out_a <= parallel_sum; out_b <= mont_result;
                    end else begin
                        out_a <= reduced_um[22:0]; out_b <= diff_um[22:0];
                    end
                    state <= 3;
                end
                3: if (b_m_ready) begin
                    out_a <= 0; out_b <= 0; state <= 0;
                end
                default: state <= 0;
            endcase
        end
    end
endmodule
