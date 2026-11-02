module rivet_h5_usehint (
    input wire clk, rst_n, clear,
    input wire a_valid,
    output wire a_ready,
    input wire [22:0] a,
    input wire hint, level44,
    output wire w_valid,
    input wire w_ready,
    output wire [5:0] w
);
    reg [1:0] state;
    reg [4:0] remaining;
    reg [22:0] dividend, quotient;
    reg [23:0] remainder;
    reg use_hint, mode44;
    reg [5:0] result;
    wire [23:0] alpha = mode44 ? 24'd190464 : 24'd523776;
    wire [23:0] gamma2 = mode44 ? 24'd95232 : 24'd261888;
    wire [23:0] shifted_rem = {remainder[22:0],dividend[22]};
    wire subtract = shifted_rem >= alpha;
    wire [23:0] next_rem = subtract ? shifted_rem-alpha : shifted_rem;
    wire [22:0] next_quotient = {quotient[21:0],subtract};
    wire [5:0] high_limit = mode44 ? 6'd44 : 6'd16;
    wire round_up = remainder > gamma2;
    wire [5:0] rounded_high = quotient[5:0] + {5'd0,round_up};
    wire wrapped = rounded_high == high_limit;
    wire [5:0] high = wrapped ? 6'd0 : rounded_high;
    wire positive_low = !wrapped && !round_up && (remainder != 0);
    wire [5:0] incremented = (high == high_limit-1'b1) ? 6'd0 : high+1'b1;
    wire [5:0] decremented = (high == 0) ? high_limit-1'b1 : high-1'b1;
    assign a_ready = rst_n && !clear && (state == 0);
    assign w_valid = rst_n && !clear && (state == 3);
    assign w = w_valid ? result : 6'd0;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 0; remaining <= 0; dividend <= 0; quotient <= 0;
            remainder <= 0; use_hint <= 0; mode44 <= 0; result <= 0;
        end else if (clear) begin
            state <= 0; remaining <= 0; dividend <= 0; quotient <= 0;
            remainder <= 0; use_hint <= 0; mode44 <= 0; result <= 0;
        end else begin
            case (state)
                0: if (a_valid && a_ready) begin
                    dividend <= a; quotient <= 0; remainder <= 0;
                    use_hint <= hint; mode44 <= level44;
                    remaining <= 23; state <= 1;
                end
                1: begin
                    dividend <= dividend << 1;
                    quotient <= next_quotient; remainder <= next_rem;
                    remaining <= remaining-1'b1;
                    if (remaining == 1) state <= 2;
                end
                2: begin
                    if (!use_hint) result <= high;
                    else if (positive_low) result <= incremented;
                    else result <= decremented;
                    state <= 3;
                end
                3: if (w_ready) begin result <= 0; state <= 0; end
                default: state <= 0;
            endcase
        end
    end
endmodule
