module rivet_h5_sampler (
    input wire clk, rst_n,
    input wire sam_cancel,
    input wire sam_cmd_valid,
    output wire sam_cmd_ready,
    input wire [2:0] sam_op,
    input wire [1:0] sam_level,
    input wire [511:0] sam_seed,
    input wire [15:0] sam_nonce,
    output wire sam_m_valid,
    input wire sam_m_ready,
    output wire [22:0] sam_m_coeff,
    output wire [7:0] sam_m_index,
    output wire sam_m_last,
    output wire sam_done_valid,
    input wire sam_done_ready,
    output wire [1:0] sam_error
);
    localparam [22:0] Q=23'd8380417;
    localparam [4:0] IDLE=0, ZERO=1, XCMD=2, SEED=3,
        UNIFORM_GET=4, UNIFORM_CHECK=5, ETA_GET=6, ETA_LO=7, ETA_HI=8,
        MASK_FILL=9, MASK_CHECK=10, SIGN_GET=11, BALL_GET=12,
        BALL_READ=13, BALL_WAIT=14, BALL_COPY=15, BALL_SIGN=16,
        OUT_READ=17, OUT_WAIT=18, OUT_SEND=19, DONE=20;
    reg [4:0] state;
    reg [2:0] op;
    reg [1:0] level, error_code;
    reg [511:0] seed;
    reg [15:0] nonce;
    reg [6:0] seed_bytes, feed_index;
    reg [7:0] index, out_index, byte_value, ball_b;
    reg [1:0] triple_index;
    reg [22:0] candidate, out_coeff;
    reg [39:0] bit_buffer;
    reg [5:0] bit_count;
    reg [63:0] signs;
    reg [3:0] sign_index;
    wire [5:0] field_bits = (level == 0) ? 6'd18 : 6'd20;
    wire [19:0] field = (level == 0) ?
        {2'd0,bit_buffer[17:0]} : bit_buffer[19:0];
    wire [22:0] gamma1 = (level == 0) ? 23'd131072 : 23'd524288;
    wire [22:0] mask_coeff = (gamma1 >= {3'd0,field}) ?
        gamma1-{3'd0,field} : Q-({3'd0,field}-gamma1);
    wire [3:0] nibble = (state == ETA_HI) ? byte_value[7:4] : byte_value[3:0];
    wire eta_four = (level == 1);
    wire eta_accept = eta_four ? (nibble < 9) : (nibble < 15);
    reg [2:0] eta_residue;
    always @* begin
        case (nibble)
            0,5,10: eta_residue=0;
            1,6,11: eta_residue=1;
            2,7,12: eta_residue=2;
            3,8,13: eta_residue=3;
            4,9,14: eta_residue=4;
            default: eta_residue=0;
        endcase
    end
    wire [22:0] eta_coeff = eta_four ?
        ((nibble <= 4) ? 23'd4-{19'd0,nibble} : Q-({19'd0,nibble}-23'd4)) :
        ((eta_residue <= 2) ? 23'd2-{20'd0,eta_residue} :
                                      Q-({20'd0,eta_residue}-23'd2));
    wire x_cmd_ready, x_s_ready, x_m_valid;
    wire [7:0] x_m_data;
    wire x_clear = sam_cancel || (state == IDLE) || (state == DONE);
    wire feed_last = (op == 4) ?
        (feed_index == seed_bytes-1'b1) : (feed_index == seed_bytes+1'b1);
    wire [7:0] feed_byte = (feed_index < seed_bytes) ?
        seed[8*feed_index +: 8] :
        ((feed_index == seed_bytes) ? nonce[7:0] : nonce[15:8]);
    wire x_take = (state == UNIFORM_GET) || (state == ETA_GET) ||
        (state == MASK_FILL) || (state == SIGN_GET) || (state == BALL_GET);
    rivet_h5_xof u_xof (
        .clk(clk), .rst_n(rst_n), .clear(x_clear),
        .cmd_valid(rst_n && !sam_cancel && (state == XCMD)),
        .cmd_ready(x_cmd_ready), .alg(op != 0),
        .s_valid(rst_n && !sam_cancel && (state == SEED)),
        .s_ready(x_s_ready), .s_data(feed_byte), .s_keep(1'b1), .s_last(feed_last),
        .m_valid(x_m_valid), .m_ready(rst_n && !sam_cancel && x_take),
        .m_data(x_m_data)
    );
    (* ramstyle="M20K", nomem2reg *) reg [22:0] poly [0:255];
    reg [22:0] ram_q;
    reg mem_we;
    reg [7:0] mem_addr;
    reg [22:0] mem_data;
    always @* begin
        mem_we=0; mem_addr=index; mem_data=0;
        case (state)
            ZERO: begin mem_we=1; mem_data=0; end
            UNIFORM_CHECK: begin mem_we=(candidate<Q); mem_data=candidate; end
            ETA_LO, ETA_HI: begin mem_we=eta_accept; mem_data=eta_coeff; end
            MASK_CHECK: begin mem_we=1; mem_data=mask_coeff; end
            BALL_COPY: begin mem_we=1; mem_data=ram_q; end
            BALL_SIGN: begin
                mem_we=1; mem_addr=ball_b; mem_data=signs[0] ? Q-1'b1 : 23'd1;
            end
            default: begin end
        endcase
    end
    always @(posedge clk) begin
        if (rst_n && !sam_cancel) begin
            if (mem_we) poly[mem_addr] <= mem_data;
            if (state == BALL_READ) ram_q <= poly[ball_b];
            if (state == OUT_READ) ram_q <= poly[out_index];
        end
    end
    assign sam_cmd_ready = rst_n && !sam_cancel && (state == IDLE);
    assign sam_m_valid = rst_n && !sam_cancel && (state == OUT_SEND);
    assign sam_m_coeff = sam_m_valid ? out_coeff : 23'd0;
    assign sam_m_index = sam_m_valid ? out_index : 8'd0;
    assign sam_m_last = sam_m_valid && (out_index == 255);
    assign sam_done_valid = rst_n && !sam_cancel && (state == DONE);
    assign sam_error = sam_done_valid ? error_code : 2'd0;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE; op <= 0; level <= 0; error_code <= 0; seed <= 0;
            nonce <= 0; seed_bytes <= 0; feed_index <= 0; index <= 0;
            out_index <= 0; byte_value <= 0; ball_b <= 0; triple_index <= 0;
            candidate <= 0; out_coeff <= 0; bit_buffer <= 0; bit_count <= 0;
            signs <= 0; sign_index <= 0;
        end else if (sam_cancel) begin
            state <= IDLE; error_code <= 0; out_coeff <= 0;
            seed <= 0; bit_buffer <= 0; bit_count <= 0; signs <= 0;
        end else begin
            case (state)
                IDLE: if (sam_cmd_valid && sam_cmd_ready) begin
                    op <= sam_op; level <= sam_level; seed <= sam_seed;
                    nonce <= sam_nonce; feed_index <= 0; index <= 0;
                    out_index <= 0; triple_index <= 0; candidate <= 0;
                    bit_buffer <= 0; bit_count <= 0; signs <= 0; sign_index <= 0;
                    error_code <= 0;
                    if ((sam_op > 4) || (sam_level == 3)) begin
                        error_code <= 1; state <= DONE;
                    end else begin
                        if (sam_op == 0) seed_bytes <= 32;
                        else if (sam_op == 4) begin
                            case (sam_level)
                                0: seed_bytes <= 32;
                                1: seed_bytes <= 48;
                                default: seed_bytes <= 64;
                            endcase
                        end else seed_bytes <= 64;
                        if (sam_op == 4) state <= ZERO;
                        else state <= XCMD;
                    end
                end
                ZERO: begin
                    if (index == 255) begin
                        case (level)
                            0: index <= 217;
                            1: index <= 207;
                            default: index <= 196;
                        endcase
                        state <= XCMD;
                    end else index <= index + 1'b1;
                end
                XCMD: if (x_cmd_ready) state <= SEED;
                SEED: if (x_s_ready) begin
                    if (feed_last) begin
                        case (op)
                            0,1: state <= UNIFORM_GET;
                            2: state <= ETA_GET;
                            3: state <= MASK_FILL;
                            default: state <= SIGN_GET;
                        endcase
                    end else feed_index <= feed_index + 1'b1;
                end
                UNIFORM_GET: if (x_m_valid) begin
                    case (triple_index)
                        0: candidate[7:0] <= x_m_data;
                        1: candidate[15:8] <= x_m_data;
                        2: candidate[22:16] <= x_m_data[6:0];
                        default: begin end
                    endcase
                    if (triple_index == 2) begin
                        triple_index <= 0; state <= UNIFORM_CHECK;
                    end else triple_index <= triple_index + 1'b1;
                end
                UNIFORM_CHECK: begin
                    if (candidate < Q) begin
                        if (index == 255) begin out_index <= 0; state <= OUT_READ; end
                        else begin index <= index + 1'b1; state <= UNIFORM_GET; end
                    end else state <= UNIFORM_GET;
                end
                ETA_GET: if (x_m_valid) begin byte_value <= x_m_data; state <= ETA_LO; end
                ETA_LO, ETA_HI: begin
                    if (eta_accept && (index == 255)) begin
                        out_index <= 0; state <= OUT_READ;
                    end else begin
                        if (eta_accept) index <= index + 1'b1;
                        if (state == ETA_LO) state <= ETA_HI;
                        else state <= ETA_GET;
                    end
                end
                MASK_FILL: if (x_m_valid) begin
                    bit_buffer <= bit_buffer | ({32'd0,x_m_data} << bit_count);
                    bit_count <= bit_count + 6'd8;
                    if (bit_count + 6'd8 >= field_bits) state <= MASK_CHECK;
                end
                MASK_CHECK: begin
                    bit_buffer <= bit_buffer >> field_bits;
                    bit_count <= bit_count - field_bits;
                    if (index == 255) begin out_index <= 0; state <= OUT_READ; end
                    else begin index <= index + 1'b1; state <= MASK_FILL; end
                end
                SIGN_GET: if (x_m_valid) begin
                    signs[8*sign_index +: 8] <= x_m_data;
                    if (sign_index == 7) state <= BALL_GET;
                    else sign_index <= sign_index + 1'b1;
                end
                BALL_GET: if (x_m_valid && (x_m_data <= index)) begin
                    ball_b <= x_m_data; state <= BALL_READ;
                end
                BALL_READ: state <= BALL_WAIT;
                BALL_WAIT: state <= BALL_COPY;
                BALL_COPY: state <= BALL_SIGN;
                BALL_SIGN: begin
                    signs <= signs >> 1;
                    if (index == 255) begin out_index <= 0; state <= OUT_READ; end
                    else begin index <= index + 1'b1; state <= BALL_GET; end
                end
                OUT_READ: state <= OUT_WAIT;
                OUT_WAIT: begin out_coeff <= ram_q; state <= OUT_SEND; end
                OUT_SEND: if (sam_m_ready) begin
                    out_coeff <= 0;
                    if (out_index == 255) state <= DONE;
                    else begin out_index <= out_index + 1'b1; state <= OUT_READ; end
                end
                DONE: if (sam_done_ready) begin error_code <= 0; state <= IDLE; end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
