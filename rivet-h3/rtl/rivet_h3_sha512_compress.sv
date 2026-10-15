module rivet_h3_sha512_compress (
    input wire clk,
    input wire rst_n,
    input wire clear,
    input wire start,
    input wire [1023:0] block_data,
    input wire [511:0] state_in,
    output wire busy,
    output reg done,
    output reg [511:0] state_out
);
    localparam [1:0] IDLE = 2'd0, ROUND = 2'd1, FEED = 2'd2;
    reg [1:0] state;
    reg [6:0] round_index;
    reg [511:0] initial_state;
    reg [63:0] a, b, c, d, e, f, g, h;
    wire [63:0] schedule_word;
    wire launch = start && (state == IDLE);
    assign busy = state != IDLE;

    rivet_h3_sha512_schedule u_schedule (
        .clk(clk), .rst_n(rst_n), .clear(clear), .load(launch),
        .step(state == ROUND), .block_data(block_data),
        .round_index(round_index), .word(schedule_word)
    );

    function [63:0] round_constant;
        input [6:0] index;
        begin
            case (index)
                0: round_constant = 64'h428a2f98d728ae22;
                1: round_constant = 64'h7137449123ef65cd;
                2: round_constant = 64'hb5c0fbcfec4d3b2f;
                3: round_constant = 64'he9b5dba58189dbbc;
                4: round_constant = 64'h3956c25bf348b538;
                5: round_constant = 64'h59f111f1b605d019;
                6: round_constant = 64'h923f82a4af194f9b;
                7: round_constant = 64'hab1c5ed5da6d8118;
                8: round_constant = 64'hd807aa98a3030242;
                9: round_constant = 64'h12835b0145706fbe;
                10: round_constant = 64'h243185be4ee4b28c;
                11: round_constant = 64'h550c7dc3d5ffb4e2;
                12: round_constant = 64'h72be5d74f27b896f;
                13: round_constant = 64'h80deb1fe3b1696b1;
                14: round_constant = 64'h9bdc06a725c71235;
                15: round_constant = 64'hc19bf174cf692694;
                16: round_constant = 64'he49b69c19ef14ad2;
                17: round_constant = 64'hefbe4786384f25e3;
                18: round_constant = 64'h0fc19dc68b8cd5b5;
                19: round_constant = 64'h240ca1cc77ac9c65;
                20: round_constant = 64'h2de92c6f592b0275;
                21: round_constant = 64'h4a7484aa6ea6e483;
                22: round_constant = 64'h5cb0a9dcbd41fbd4;
                23: round_constant = 64'h76f988da831153b5;
                24: round_constant = 64'h983e5152ee66dfab;
                25: round_constant = 64'ha831c66d2db43210;
                26: round_constant = 64'hb00327c898fb213f;
                27: round_constant = 64'hbf597fc7beef0ee4;
                28: round_constant = 64'hc6e00bf33da88fc2;
                29: round_constant = 64'hd5a79147930aa725;
                30: round_constant = 64'h06ca6351e003826f;
                31: round_constant = 64'h142929670a0e6e70;
                32: round_constant = 64'h27b70a8546d22ffc;
                33: round_constant = 64'h2e1b21385c26c926;
                34: round_constant = 64'h4d2c6dfc5ac42aed;
                35: round_constant = 64'h53380d139d95b3df;
                36: round_constant = 64'h650a73548baf63de;
                37: round_constant = 64'h766a0abb3c77b2a8;
                38: round_constant = 64'h81c2c92e47edaee6;
                39: round_constant = 64'h92722c851482353b;
                40: round_constant = 64'ha2bfe8a14cf10364;
                41: round_constant = 64'ha81a664bbc423001;
                42: round_constant = 64'hc24b8b70d0f89791;
                43: round_constant = 64'hc76c51a30654be30;
                44: round_constant = 64'hd192e819d6ef5218;
                45: round_constant = 64'hd69906245565a910;
                46: round_constant = 64'hf40e35855771202a;
                47: round_constant = 64'h106aa07032bbd1b8;
                48: round_constant = 64'h19a4c116b8d2d0c8;
                49: round_constant = 64'h1e376c085141ab53;
                50: round_constant = 64'h2748774cdf8eeb99;
                51: round_constant = 64'h34b0bcb5e19b48a8;
                52: round_constant = 64'h391c0cb3c5c95a63;
                53: round_constant = 64'h4ed8aa4ae3418acb;
                54: round_constant = 64'h5b9cca4f7763e373;
                55: round_constant = 64'h682e6ff3d6b2b8a3;
                56: round_constant = 64'h748f82ee5defb2fc;
                57: round_constant = 64'h78a5636f43172f60;
                58: round_constant = 64'h84c87814a1f0ab72;
                59: round_constant = 64'h8cc702081a6439ec;
                60: round_constant = 64'h90befffa23631e28;
                61: round_constant = 64'ha4506cebde82bde9;
                62: round_constant = 64'hbef9a3f7b2c67915;
                63: round_constant = 64'hc67178f2e372532b;
                64: round_constant = 64'hca273eceea26619c;
                65: round_constant = 64'hd186b8c721c0c207;
                66: round_constant = 64'heada7dd6cde0eb1e;
                67: round_constant = 64'hf57d4f7fee6ed178;
                68: round_constant = 64'h06f067aa72176fba;
                69: round_constant = 64'h0a637dc5a2c898a6;
                70: round_constant = 64'h113f9804bef90dae;
                71: round_constant = 64'h1b710b35131c471b;
                72: round_constant = 64'h28db77f523047d84;
                73: round_constant = 64'h32caab7b40c72493;
                74: round_constant = 64'h3c9ebe0a15c9bebc;
                75: round_constant = 64'h431d67c49c100d4c;
                76: round_constant = 64'h4cc5d4becb3e42b6;
                77: round_constant = 64'h597f299cfc657e2a;
                78: round_constant = 64'h5fcb6fab3ad6faec;
                79: round_constant = 64'h6c44198c4a475817;
                default: round_constant = 64'd0;
            endcase
        end
    endfunction

    wire [63:0] big_sigma0 = {a[27:0], a[63:28]} ^
                            {a[33:0], a[63:34]} ^
                            {a[38:0], a[63:39]};
    wire [63:0] big_sigma1 = {e[13:0], e[63:14]} ^
                            {e[17:0], e[63:18]} ^
                            {e[40:0], e[63:41]};
    wire [63:0] choose = (e & f) ^ (~e & g);
    wire [63:0] majority = (a & b) ^ (a & c) ^ (b & c);
    wire [63:0] temp1 = h + big_sigma1 + choose +
                        round_constant(round_index) + schedule_word;
    wire [63:0] temp2 = big_sigma0 + majority;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            round_index <= 7'd0;
            initial_state <= 512'd0;
            a <= 64'd0; b <= 64'd0; c <= 64'd0; d <= 64'd0;
            e <= 64'd0; f <= 64'd0; g <= 64'd0; h <= 64'd0;
            done <= 1'b0;
            state_out <= 512'd0;
        end else if (clear) begin
            state <= IDLE;
            round_index <= 7'd0;
            initial_state <= 512'd0;
            a <= 64'd0; b <= 64'd0; c <= 64'd0; d <= 64'd0;
            e <= 64'd0; f <= 64'd0; g <= 64'd0; h <= 64'd0;
            done <= 1'b0;
            state_out <= 512'd0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: begin
                    if (start) begin
                        initial_state <= state_in;
                        {a, b, c, d, e, f, g, h} <= state_in;
                        round_index <= 7'd0;
                        state <= ROUND;
                    end
                end
                ROUND: begin
                    a <= temp1 + temp2;
                    b <= a; c <= b; d <= c;
                    e <= d + temp1;
                    f <= e; g <= f; h <= g;
                    if (round_index == 7'd79)
                        state <= FEED;
                    else
                        round_index <= round_index + 7'd1;
                end
                FEED: begin
                    state_out <= {
                        initial_state[511:448] + a,
                        initial_state[447:384] + b,
                        initial_state[383:320] + c,
                        initial_state[319:256] + d,
                        initial_state[255:192] + e,
                        initial_state[191:128] + f,
                        initial_state[127:64] + g,
                        initial_state[63:0] + h
                    };
                    done <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
