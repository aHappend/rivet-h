module rivet_h5_montgomery (
    input wire clk, rst_n,
    input wire a_valid,
    output wire a_ready,
    input wire [22:0] a, b,
    output wire m_valid,
    input wire m_ready,
    output wire [22:0] m
);
    localparam [23:0] Q = 24'd8380417;
    reg [3:0] stage;
    reg [22:0] ar, br, result;
    reg [31:0] p00, p01, p10, p11;
    reg [47:0] t_left, t_right;
    reg [45:0] t;
    reg [31:0] r00, r01, r10;
    reg [32:0] cross_sum;
    reg [31:0] reduction_word;
    reg [31:0] q00, q01, q10, q11;
    reg [55:0] q_left, q_right, mq;
    reg [56:0] total;
    wire [24:0] upper = total[56:32];
    wire [24:0] normalized =
        (upper >= {1'b0,Q}) ? upper - {1'b0,Q} : upper;
    assign a_ready = rst_n && (stage == 0);
    assign m_valid = rst_n && (stage == 12);
    assign m = m_valid ? result : 23'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stage <= 0;
            ar <= 0; br <= 0; result <= 0;
            p00 <= 0; p01 <= 0; p10 <= 0; p11 <= 0;
            t_left <= 0; t_right <= 0; t <= 0;
            r00 <= 0; r01 <= 0; r10 <= 0; cross_sum <= 0;
            reduction_word <= 0;
            q00 <= 0; q01 <= 0; q10 <= 0; q11 <= 0;
            q_left <= 0; q_right <= 0; mq <= 0; total <= 0;
        end else begin
            case (stage)
                0: if (a_valid && a_ready) begin
                    ar <= a; br <= b; stage <= 1;
                end
                1: begin
                    p00 <= ar[15:0] * br[15:0];
                    p01 <= ar[15:0] * br[22:16];
                    p10 <= ar[22:16] * br[15:0];
                    p11 <= ar[22:16] * br[22:16];
                    stage <= 2;
                end
                2: begin
                    t_left <= {16'd0,p00} + {p01,16'd0};
                    t_right <= {p10,16'd0} + {p11[15:0],32'd0};
                    stage <= 3;
                end
                3: begin t <= t_left + t_right; stage <= 4; end
                4: begin
                    r00 <= t[15:0] * 16'd57343;
                    r01 <= t[15:0] * 16'd64639;
                    r10 <= t[31:16] * 16'd57343;
                    stage <= 5;
                end
                5: begin
                    cross_sum <= {1'b0,r01} + {1'b0,r10};
                    stage <= 6;
                end
                6: begin
                    reduction_word <= r00 + {cross_sum[15:0],16'd0};
                    stage <= 7;
                end
                7: begin
                    q00 <= reduction_word[15:0] * 16'hE001;
                    q01 <= reduction_word[15:0] * 7'h7F;
                    q10 <= reduction_word[31:16] * 16'hE001;
                    q11 <= reduction_word[31:16] * 7'h7F;
                    stage <= 8;
                end
                8: begin
                    q_left <= {24'd0,q00} + {8'd0,q01,16'd0};
                    q_right <= {8'd0,q10,16'd0} + {q11[23:0],32'd0};
                    stage <= 9;
                end
                9: begin mq <= q_left + q_right; stage <= 10; end
                10: begin
                    total <= {1'b0,mq} + {11'd0,t};
                    stage <= 11;
                end
                11: begin result <= normalized[22:0]; stage <= 12; end
                12: if (m_ready) begin result <= 0; stage <= 0; end
                default: stage <= 0;
            endcase
        end
    end
endmodule
