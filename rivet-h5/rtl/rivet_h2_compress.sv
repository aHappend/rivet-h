// Compression arithmetic and timing derived from supplied rivet_h1_compress.
module rivet_h2_compress (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         clear,
    input  wire         start,
    input  wire [511:0] block_data,
    input  wire [255:0] state_in,
    output wire         busy,
    output reg          done,
    output reg  [255:0] state_out
);
    localparam [1:0] IDLE = 2'd0, ROUND = 2'd1, FEED = 2'd2;
    reg [1:0] state;
    reg [5:0] round_index;
    reg [255:0] initial_state;
    reg [31:0] a, b, c, d, e, f, g, h;
    reg [2:0] phase;
    reg [31:0] sigma0_reg, sigma1_reg, choose_reg, majority_reg, constant_reg;
    reg [31:0] pair_h, pair_ck, sum_hck, word_reg, temp1_reg, temp2_reg;
    wire launch = start && (state == IDLE);
    wire [31:0] schedule_word;
    assign busy = state != IDLE;

    rivet_h2_schedule u_schedule (
        .clk(clk), .rst_n(rst_n), .clear(clear), .load(launch),
        .step((state == ROUND) && (phase == 3'd4)), .block_data(block_data),
        .round_index(round_index), .word(schedule_word)
    );

    function [31:0] round_constant;
        input [5:0] index;
        begin
            case (index)
                0: round_constant = 32'h428a2f98;
                1: round_constant = 32'h71374491;
                2: round_constant = 32'hb5c0fbcf;
                3: round_constant = 32'he9b5dba5;
                4: round_constant = 32'h3956c25b;
                5: round_constant = 32'h59f111f1;
                6: round_constant = 32'h923f82a4;
                7: round_constant = 32'hab1c5ed5;
                8: round_constant = 32'hd807aa98;
                9: round_constant = 32'h12835b01;
                10: round_constant = 32'h243185be;
                11: round_constant = 32'h550c7dc3;
                12: round_constant = 32'h72be5d74;
                13: round_constant = 32'h80deb1fe;
                14: round_constant = 32'h9bdc06a7;
                15: round_constant = 32'hc19bf174;
                16: round_constant = 32'he49b69c1;
                17: round_constant = 32'hefbe4786;
                18: round_constant = 32'h0fc19dc6;
                19: round_constant = 32'h240ca1cc;
                20: round_constant = 32'h2de92c6f;
                21: round_constant = 32'h4a7484aa;
                22: round_constant = 32'h5cb0a9dc;
                23: round_constant = 32'h76f988da;
                24: round_constant = 32'h983e5152;
                25: round_constant = 32'ha831c66d;
                26: round_constant = 32'hb00327c8;
                27: round_constant = 32'hbf597fc7;
                28: round_constant = 32'hc6e00bf3;
                29: round_constant = 32'hd5a79147;
                30: round_constant = 32'h06ca6351;
                31: round_constant = 32'h14292967;
                32: round_constant = 32'h27b70a85;
                33: round_constant = 32'h2e1b2138;
                34: round_constant = 32'h4d2c6dfc;
                35: round_constant = 32'h53380d13;
                36: round_constant = 32'h650a7354;
                37: round_constant = 32'h766a0abb;
                38: round_constant = 32'h81c2c92e;
                39: round_constant = 32'h92722c85;
                40: round_constant = 32'ha2bfe8a1;
                41: round_constant = 32'ha81a664b;
                42: round_constant = 32'hc24b8b70;
                43: round_constant = 32'hc76c51a3;
                44: round_constant = 32'hd192e819;
                45: round_constant = 32'hd6990624;
                46: round_constant = 32'hf40e3585;
                47: round_constant = 32'h106aa070;
                48: round_constant = 32'h19a4c116;
                49: round_constant = 32'h1e376c08;
                50: round_constant = 32'h2748774c;
                51: round_constant = 32'h34b0bcb5;
                52: round_constant = 32'h391c0cb3;
                53: round_constant = 32'h4ed8aa4a;
                54: round_constant = 32'h5b9cca4f;
                55: round_constant = 32'h682e6ff3;
                56: round_constant = 32'h748f82ee;
                57: round_constant = 32'h78a5636f;
                58: round_constant = 32'h84c87814;
                59: round_constant = 32'h8cc70208;
                60: round_constant = 32'h90befffa;
                61: round_constant = 32'ha4506ceb;
                62: round_constant = 32'hbef9a3f7;
                63: round_constant = 32'hc67178f2;
                default: round_constant = 32'd0;
            endcase
        end
    endfunction

    wire [31:0] big_sigma0 = {a[1:0], a[31:2]} ^
                            {a[12:0], a[31:13]} ^
                            {a[21:0], a[31:22]};
    wire [31:0] big_sigma1 = {e[5:0], e[31:6]} ^
                            {e[10:0], e[31:11]} ^
                            {e[24:0], e[31:25]};
    wire [31:0] choose = (e & f) ^ (~e & g);
    wire [31:0] majority = (a & b) ^ (a & c) ^ (b & c);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            round_index <= 6'd0;
            initial_state <= 256'd0;
            a <= 32'd0; b <= 32'd0; c <= 32'd0; d <= 32'd0;
            e <= 32'd0; f <= 32'd0; g <= 32'd0; h <= 32'd0;
            done <= 1'b0;
            state_out <= 256'd0;
            phase <= 3'd0;
            sigma0_reg <= 32'd0; sigma1_reg <= 32'd0;
            choose_reg <= 32'd0; majority_reg <= 32'd0; constant_reg <= 32'd0;
            pair_h <= 32'd0; pair_ck <= 32'd0; sum_hck <= 32'd0;
            word_reg <= 32'd0; temp1_reg <= 32'd0; temp2_reg <= 32'd0;
        end else if (clear) begin
            state <= IDLE;
            round_index <= 6'd0;
            initial_state <= 256'd0;
            a <= 32'd0; b <= 32'd0; c <= 32'd0; d <= 32'd0;
            e <= 32'd0; f <= 32'd0; g <= 32'd0; h <= 32'd0;
            done <= 1'b0;
            state_out <= 256'd0;
            phase <= 3'd0;
            sigma0_reg <= 32'd0; sigma1_reg <= 32'd0;
            choose_reg <= 32'd0; majority_reg <= 32'd0; constant_reg <= 32'd0;
            pair_h <= 32'd0; pair_ck <= 32'd0; sum_hck <= 32'd0;
            word_reg <= 32'd0; temp1_reg <= 32'd0; temp2_reg <= 32'd0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: begin
                    if (start) begin
                        initial_state <= state_in;
                        {a, b, c, d, e, f, g, h} <= state_in;
                        round_index <= 6'd0;
                        phase <= 3'd0;
                        state <= ROUND;
                    end
                end
                ROUND: begin
                    case (phase)
                        3'd0: begin
                            sigma0_reg <= big_sigma0;
                            sigma1_reg <= big_sigma1;
                            choose_reg <= choose;
                            majority_reg <= majority;
                            constant_reg <= round_constant(round_index);
                            phase <= 3'd1;
                        end
                        3'd1: begin
                            pair_h <= h + sigma1_reg;
                            pair_ck <= choose_reg + constant_reg;
                            temp2_reg <= sigma0_reg + majority_reg;
                            phase <= 3'd2;
                        end
                        3'd2: begin
                            sum_hck <= pair_h + pair_ck;
                            word_reg <= schedule_word;
                            phase <= 3'd3;
                        end
                        3'd3: begin
                            temp1_reg <= sum_hck + word_reg;
                            phase <= 3'd4;
                        end
                        3'd4: begin
                            a <= temp1_reg + temp2_reg;
                            b <= a; c <= b; d <= c;
                            e <= d + temp1_reg;
                            f <= e; g <= f; h <= g;
                            phase <= 3'd0;
                            if (round_index == 6'd63)
                                state <= FEED;
                            else
                                round_index <= round_index + 6'd1;
                        end
                        default: phase <= 3'd0;
                    endcase
                end
                FEED: begin
                    state_out <= {
                        initial_state[255:224] + a,
                        initial_state[223:192] + b,
                        initial_state[191:160] + c,
                        initial_state[159:128] + d,
                        initial_state[127:96] + e,
                        initial_state[95:64] + f,
                        initial_state[63:32] + g,
                        initial_state[31:0] + h
                    };
                    done <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
