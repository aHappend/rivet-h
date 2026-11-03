module rivet_h4_keccak (
    input wire clk,
    input wire rst_n,
    input wire clear,
    input wire start,
    input wire [1599:0] state_in,
    output wire busy,
    output reg done,
    output reg [1599:0] state_out
);
    reg running;
    reg [1:0] phase;
    reg [4:0] round_index;
    reg [1599:0] lanes, rho_pi, chi;
    reg [63:0] parity [0:4];
    wire [1599:0] theta_rho_pi;
    wire [1599:0] chi_next;
    wire [1599:0] iota_next =
        chi ^ {1536'd0, round_constant(round_index)};
    assign busy = rst_n && running;

    function [63:0] round_constant;
        input [4:0] index;
        begin
            case (index)
                0: round_constant = 64'h0000000000000001;
                1: round_constant = 64'h0000000000008082;
                2: round_constant = 64'h800000000000808a;
                3: round_constant = 64'h8000000080008000;
                4: round_constant = 64'h000000000000808b;
                5: round_constant = 64'h0000000080000001;
                6: round_constant = 64'h8000000080008081;
                7: round_constant = 64'h8000000000008009;
                8: round_constant = 64'h000000000000008a;
                9: round_constant = 64'h0000000000000088;
                10: round_constant = 64'h0000000080008009;
                11: round_constant = 64'h000000008000000a;
                12: round_constant = 64'h000000008000808b;
                13: round_constant = 64'h800000000000008b;
                14: round_constant = 64'h8000000000008089;
                15: round_constant = 64'h8000000000008003;
                16: round_constant = 64'h8000000000008002;
                17: round_constant = 64'h8000000000000080;
                18: round_constant = 64'h000000000000800a;
                19: round_constant = 64'h800000008000000a;
                20: round_constant = 64'h8000000080008081;
                21: round_constant = 64'h8000000000008080;
                22: round_constant = 64'h0000000080000001;
                23: round_constant = 64'h8000000080008008;
                default: round_constant = 64'd0;
            endcase
        end
    endfunction

    function integer rotation;
        input integer index;
        begin
            case (index)
                0: rotation = 0;
                1: rotation = 1;
                2: rotation = 62;
                3: rotation = 28;
                4: rotation = 27;
                5: rotation = 36;
                6: rotation = 44;
                7: rotation = 6;
                8: rotation = 55;
                9: rotation = 20;
                10: rotation = 3;
                11: rotation = 10;
                12: rotation = 43;
                13: rotation = 25;
                14: rotation = 39;
                15: rotation = 41;
                16: rotation = 45;
                17: rotation = 15;
                18: rotation = 21;
                19: rotation = 8;
                20: rotation = 18;
                21: rotation = 2;
                22: rotation = 61;
                23: rotation = 56;
                24: rotation = 14;
                default: rotation = 0;
            endcase
        end
    endfunction

    genvar x, y;
    generate
        for (x = 0; x < 5; x = x + 1) begin : g_x
            localparam integer LEFT = (x == 0) ? 4 : x - 1;
            localparam integer RIGHT = (x == 4) ? 0 : x + 1;
            localparam integer RIGHT2 = (x >= 3) ? x - 3 : x + 2;
            for (y = 0; y < 5; y = y + 1) begin : g_y
                localparam integer OFFSET = rotation(x + 5*y);
                localparam integer PI_SUM = 2*x + 3*y;
                localparam integer PI_Y = (PI_SUM >= 20) ? PI_SUM - 20 :
                                         (PI_SUM >= 15) ? PI_SUM - 15 :
                                         (PI_SUM >= 10) ? PI_SUM - 10 :
                                         (PI_SUM >= 5) ? PI_SUM - 5 : PI_SUM;
                wire [63:0] theta_lane = lanes[64*(x+5*y) +: 64] ^
                    parity[LEFT] ^ {parity[RIGHT][62:0], parity[RIGHT][63]};
                if (OFFSET == 0) begin : g_no_rotate
                    assign theta_rho_pi[64*(y+5*PI_Y) +: 64] = theta_lane;
                end else begin : g_rotate
                    assign theta_rho_pi[64*(y+5*PI_Y) +: 64] =
                        {theta_lane[63-OFFSET:0], theta_lane[63:64-OFFSET]};
                end
                assign chi_next[64*(x+5*y) +: 64] =
                    rho_pi[64*(x+5*y) +: 64] ^
                    ((~rho_pi[64*(RIGHT+5*y) +: 64]) &
                     rho_pi[64*(RIGHT2+5*y) +: 64]);
            end
        end
    endgenerate

    integer column;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            running <= 1'b0;
            phase <= 2'd0;
            round_index <= 5'd0;
            lanes <= 1600'd0;
            rho_pi <= 1600'd0;
            chi <= 1600'd0;
            state_out <= 1600'd0;
            done <= 1'b0;
            for (column = 0; column < 5; column = column + 1)
                parity[column] <= 64'd0;
        end else if (clear) begin
            running <= 1'b0;
            phase <= 2'd0;
            round_index <= 5'd0;
            lanes <= 1600'd0;
            rho_pi <= 1600'd0;
            chi <= 1600'd0;
            state_out <= 1600'd0;
            done <= 1'b0;
            for (column = 0; column < 5; column = column + 1)
                parity[column] <= 64'd0;
        end else begin
            done <= 1'b0;
            if (!running) begin
                if (start) begin
                    lanes <= state_in;
                    phase <= 2'd0;
                    round_index <= 5'd0;
                    running <= 1'b1;
                end
            end else begin
                case (phase)
                    2'd0: begin
                        for (column = 0; column < 5; column = column + 1)
                            parity[column] <= lanes[64*column +: 64] ^
                                lanes[64*(column+5) +: 64] ^
                                lanes[64*(column+10) +: 64] ^
                                lanes[64*(column+15) +: 64] ^
                                lanes[64*(column+20) +: 64];
                        phase <= 2'd1;
                    end
                    2'd1: begin
                        rho_pi <= theta_rho_pi;
                        phase <= 2'd2;
                    end
                    2'd2: begin
                        chi <= chi_next;
                        phase <= 2'd3;
                    end
                    2'd3: begin
                        lanes <= iota_next;
                        phase <= 2'd0;
                        if (round_index == 5'd23) begin
                            state_out <= iota_next;
                            running <= 1'b0;
                            done <= 1'b1;
                        end else
                            round_index <= round_index + 5'd1;
                    end
                endcase
            end
        end
    end
endmodule
