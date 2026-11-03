module rivet_h5_verify (
    input wire clk, rst_n,
    input wire pq_cmd_valid,
    output wire pq_cmd_ready,
    input wire [1:0] pq_cmd_op, pq_level,
    input wire [7:0] pq_ctx_bytes,
    input wire [31:0] pq_message_bytes,
    input wire pq_s_valid,
    output wire pq_s_ready,
    input wire [1:0] pq_s_kind,
    input wire [31:0] pq_s_data,
    input wire [3:0] pq_s_keep,
    input wire pq_s_last,
    output wire pq_result_valid,
    input wire pq_result_ready,
    output wire pq_auth_ok,
    output wire [3:0] pq_status,
    output wire pq_key_locked
);
    localparam [22:0] Q=23'd8380417;
    localparam [7:0] IDLE=0, RX=1, RX_DRAIN=2, RESULT=3,
        H_CLEAR=4, H_CMD=5, PK_READ=6, PK_WAIT=7, PK_SEND=8, TR_OUT=9,
        C_READ=10, C_WAIT=11, C_STORE=12, Z_INIT=13, Z_NEED=14,
        Z_READ=15, Z_WAIT=16, Z_PACK=17, Z_FIELD=18, Z_NEXT=19,
        N_CMD=20, N_READ=21, N_WAIT=22, N_SEND=23, N_OUT=24, N_DONE=25,
        H_ZERO=26, H_END_READ=27, H_END_WAIT=28, H_END_CHECK=29,
        H_ROW=30, H_IDX_READ=31, H_IDX_WAIT=32, H_IDX_CHECK=33,
        H_UNUSED=34, H_UN_READ=35, H_UN_WAIT=36, H_UN_CHECK=37,
        MU_SETUP=38, MU_PREFIX=39, MU_OUT=40, C_SAMPLE=41,
        SAM_CMD=42, SAM_OUT=43, SAM_DONE=44, C_NTT=45,
        CHECK_SETUP=46, CHECK_PREFIX=47, ROW_CLEAR=48, MATRIX_START=49,
        PROD_INIT=50, PROD_READ=51, PROD_WAIT=52, PROD_SEND=53,
        PROD_RESULT=54, CONV_SEND=55, CONV_RESULT=56, ACC_WRITE=57,
        PROD_NEXT=58, T1_INIT=59, T1_NEED=60, T1_READ=61, T1_WAIT=62,
        T1_PACK=63, T1_FIELD=64, T1_NTT=65, SUB_INIT=66, INV_NTT=67,
        W_INIT=68, W_READ=69, W_WAIT=70, W_SEND=71, W_RESULT=72,
        W_DRAIN=73, W_NEXT=74, CC_OUT=75;
    localparam [1:0] NT_Z=0, NT_C=1, NT_T1=2, NT_ACC=3;
    reg [7:0] state, hash_return, ntt_return, sampler_return;
    reg [1:0] level, key_level, rx_kind, ntt_task;
    reg locked, auth, mismatch;
    reg [3:0] status;
    reg [7:0] context_length;
    reg [31:0] message_length;
    reg [32:0] rx_length, rx_received;
    reg [31:0] rx_word;
    reg [2:0] rx_beat_bytes, rx_byte_index;
    reg rx_last;
    reg [511:0] tr, mu, challenge, reconstructed_challenge;
    reg [255:0] rho;
    reg [12:0] sig_cursor;
    reg [11:0] pk_cursor;
    reg [6:0] hash_index;
    reg [2:0] z_poly, col, row;
    reg [7:0] coeff_index, ntt_index;
    reg [39:0] decode_bits;
    reg [5:0] decode_count;
    reg [11:0] hint_clear_index;
    reg [3:0] hint_row;
    reg [7:0] hint_cursor, previous_endpoint, previous_hint;
    reg first_hint;
    reg [7:0] endpoints [0:7];
    reg [2:0] sampler_op;
    reg [511:0] sampler_seed;
    reg [15:0] sampler_nonce;
    reg subtract_product;
    reg [22:0] product_mid, product_normal;
    reg [15:0] w_bits;
    reg [4:0] w_count;
    wire [3:0] k = (level == 0) ? 4'd4 : ((level == 1) ? 4'd6 : 4'd8);
    wire [3:0] l = (level == 0) ? 4'd4 : ((level == 1) ? 4'd5 : 4'd7);
    wire [6:0] c_bytes = (level == 0) ? 7'd32 : ((level == 1) ? 7'd48 : 7'd64);
    wire [7:0] omega = (level == 0) ? 8'd80 : ((level == 1) ? 8'd55 : 8'd75);
    wire [11:0] pk_bytes = (level == 0) ? 12'd1312 :
        ((level == 1) ? 12'd1952 : 12'd2592);
    wire [12:0] sig_bytes = (level == 0) ? 13'd2420 :
        ((level == 1) ? 13'd3309 : 13'd4627);
    wire [12:0] hint_base = (level == 0) ? 13'd2336 :
        ((level == 1) ? 13'd3248 : 13'd4544);
    wire [5:0] z_width = (level == 0) ? 6'd18 : 6'd20;
    wire [22:0] gamma1 = (level == 0) ? 23'd131072 : 23'd524288;
    wire [22:0] norm_limit = (level == 0) ? 23'd130994 :
        ((level == 1) ? 23'd524092 : 23'd524168);
    wire [19:0] z_field = (level == 0) ?
        {2'd0,decode_bits[17:0]} : decode_bits[19:0];
    wire [22:0] z_magnitude = ({3'd0,z_field} >= gamma1) ?
        {3'd0,z_field}-gamma1 : gamma1-{3'd0,z_field};
    wire [22:0] z_coeff = ({3'd0,z_field} <= gamma1) ?
        gamma1-{3'd0,z_field} : Q-({3'd0,z_field}-gamma1);
    wire cancel = rst_n && pq_cmd_valid && pq_cmd_ready && (pq_cmd_op == 2);
    assign pq_cmd_ready = rst_n && ((pq_cmd_op == 2) || (state == IDLE));
    assign pq_s_ready = rst_n && !cancel && (state == RX);
    assign pq_result_valid = rst_n && !cancel && (state == RESULT);
    assign pq_auth_ok = pq_result_valid && auth;
    assign pq_status = pq_result_valid ? status : 4'd0;
    assign pq_key_locked = rst_n && locked;

    reg [2:0] beat_bytes;
    reg keep_legal;
    always @* begin
        beat_bytes=0; keep_legal=0;
        case (pq_s_keep)
            4'b1111: begin beat_bytes=4; keep_legal=1; end
            4'b1110: begin beat_bytes=3; keep_legal=pq_s_last; end
            4'b1100: begin beat_bytes=2; keep_legal=pq_s_last; end
            4'b1000: begin beat_bytes=1; keep_legal=pq_s_last; end
            4'b0000: begin
                beat_bytes=0;
                keep_legal=pq_s_last && (rx_length == 0) && (rx_kind >= 2);
            end
            default: begin end
        endcase
    end
    wire [32:0] proposed_received = rx_received + {30'd0,beat_bytes};
    wire framing_legal = keep_legal && (pq_s_kind == rx_kind) &&
        (proposed_received <= rx_length) &&
        (pq_s_last == (proposed_received == rx_length));
    wire raw_write = pq_s_valid && pq_s_ready && framing_legal;
    wire [10:0] raw_waddr = rx_received[12:2];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] pk_b0 [0:647];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] pk_b1 [0:647];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] pk_b2 [0:647];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] pk_b3 [0:647];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] sig_b0 [0:1156];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] sig_b1 [0:1156];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] sig_b2 [0:1156];
    (* ramstyle="M20K", nomem2reg *) reg [7:0] sig_b3 [0:1156];
    wire pk_read = (state == PK_READ) || (state == T1_READ);
    wire sig_read = (state == C_READ) || (state == Z_READ) ||
        (state == H_END_READ) || (state == H_IDX_READ) || (state == H_UN_READ);
    wire [12:0] sig_raddr = (state == H_END_READ) ?
        hint_base+{5'd0,omega}+{9'd0,hint_row} :
        (((state == H_IDX_READ) || (state == H_UN_READ)) ?
        hint_base+{5'd0,hint_cursor} : sig_cursor);
    reg [7:0] pk_q0, pk_q1, pk_q2, pk_q3, sig_q0, sig_q1, sig_q2, sig_q3;
    reg [1:0] pk_lane, sig_lane;
    wire [7:0] pk_byte = (pk_lane == 0) ? pk_q0 :
        ((pk_lane == 1) ? pk_q1 : ((pk_lane == 2) ? pk_q2 : pk_q3));
    wire [7:0] sig_byte = (sig_lane == 0) ? sig_q0 :
        ((sig_lane == 1) ? sig_q1 : ((sig_lane == 2) ? sig_q2 : sig_q3));
    always @(posedge clk) begin
        if (rst_n && !cancel) begin
            if (raw_write && (rx_kind == 0) && !locked) begin
                if (pq_s_keep[3]) pk_b0[raw_waddr] <= pq_s_data[31:24];
                if (pq_s_keep[2]) pk_b1[raw_waddr] <= pq_s_data[23:16];
                if (pq_s_keep[1]) pk_b2[raw_waddr] <= pq_s_data[15:8];
                if (pq_s_keep[0]) pk_b3[raw_waddr] <= pq_s_data[7:0];
            end
            if (raw_write && (rx_kind == 1)) begin
                if (pq_s_keep[3]) sig_b0[raw_waddr] <= pq_s_data[31:24];
                if (pq_s_keep[2]) sig_b1[raw_waddr] <= pq_s_data[23:16];
                if (pq_s_keep[1]) sig_b2[raw_waddr] <= pq_s_data[15:8];
                if (pq_s_keep[0]) sig_b3[raw_waddr] <= pq_s_data[7:0];
            end
            if (pk_read) begin
                pk_q0 <= pk_b0[pk_cursor[11:2]]; pk_q1 <= pk_b1[pk_cursor[11:2]];
                pk_q2 <= pk_b2[pk_cursor[11:2]]; pk_q3 <= pk_b3[pk_cursor[11:2]];
                pk_lane <= pk_cursor[1:0];
            end
            if (sig_read) begin
                sig_q0 <= sig_b0[sig_raddr[12:2]]; sig_q1 <= sig_b1[sig_raddr[12:2]];
                sig_q2 <= sig_b2[sig_raddr[12:2]]; sig_q3 <= sig_b3[sig_raddr[12:2]];
                sig_lane <= sig_raddr[1:0];
            end
        end
    end

    wire hash_cmd_ready, hash_s_ready, hash_m_valid;
    wire [7:0] hash_m_data;
    reg hash_s_valid, hash_s_last;
    reg [7:0] hash_s_data;
    wire hash_clear = cancel || (state == IDLE) || (state == RESULT) || (state == H_CLEAR);
    always @* begin
        hash_s_valid=0; hash_s_data=0; hash_s_last=0;
        if (rst_n && !cancel) begin
            case (state)
                PK_SEND: begin
                    hash_s_valid=1; hash_s_data=pk_byte;
                    hash_s_last=(pk_cursor == pk_bytes-1'b1);
                end
                MU_PREFIX: begin
                    hash_s_valid=1;
                    if (hash_index < 64) hash_s_data=tr[8*hash_index +: 8];
                    else if (hash_index == 64) hash_s_data=0;
                    else hash_s_data=context_length;
                    hash_s_last=(hash_index == 65) &&
                        (context_length == 0) && (message_length == 0);
                end
                RX_DRAIN: begin
                    hash_s_valid=1;
                    hash_s_data=rx_word[31-8*rx_byte_index -: 8];
                    hash_s_last=rx_last && (rx_byte_index == rx_beat_bytes-1'b1) &&
                        ((rx_kind == 3) || ((rx_kind == 2) && (message_length == 0)));
                end
                CHECK_PREFIX: begin
                    hash_s_valid=1; hash_s_data=mu[8*hash_index +: 8];
                end
                W_DRAIN: begin
                    hash_s_valid=1; hash_s_data=w_bits[7:0];
                    hash_s_last=({1'b0,row} == k-1'b1) &&
                        (coeff_index == 255) && (w_count == 8);
                end
                default: begin end
            endcase
        end
    end
    rivet_h5_xof u_hash (
        .clk(clk), .rst_n(rst_n), .clear(hash_clear),
        .cmd_valid(rst_n && !cancel && (state == H_CMD)),
        .cmd_ready(hash_cmd_ready), .alg(1'b1),
        .s_valid(hash_s_valid), .s_ready(hash_s_ready),
        .s_data(hash_s_data), .s_keep(1'b1), .s_last(hash_s_last),
        .m_valid(hash_m_valid),
        .m_ready(rst_n && !cancel &&
            ((state == TR_OUT) || (state == MU_OUT) || (state == CC_OUT))),
        .m_data(hash_m_data)
    );

    wire n_cmd_ready, n_s_ready, n_m_valid, n_m_last, n_done_valid;
    wire [22:0] n_m_coeff;
    wire [7:0] n_m_index;
    wire [1:0] n_error;
    reg [22:0] scratch_q, accum_q, prod_a_q, prod_b_q;
    reg hint_q;
    rivet_h5_ntt u_ntt (
        .clk(clk), .rst_n(rst_n), .n_cancel(cancel),
        .n_cmd_valid(rst_n && !cancel && (state == N_CMD)), .n_cmd_ready(n_cmd_ready),
        .n_inverse(ntt_task == NT_ACC),
        .n_s_valid(rst_n && !cancel && (state == N_SEND)), .n_s_ready(n_s_ready),
        .n_s_coeff((ntt_task == NT_ACC) ? accum_q : scratch_q),
        .n_s_last(ntt_index == 255), .n_m_valid(n_m_valid),
        .n_m_ready(rst_n && !cancel && (state == N_OUT)), .n_m_coeff(n_m_coeff),
        .n_m_index(n_m_index), .n_m_last(n_m_last),
        .n_done_valid(n_done_valid), .n_done_ready(rst_n && !cancel && (state == N_DONE)),
        .n_error(n_error)
    );
    wire sam_cmd_ready, sam_m_valid, sam_m_last, sam_done_valid;
    wire [22:0] sam_m_coeff;
    wire [7:0] sam_m_index;
    wire [1:0] sam_error;
    rivet_h5_sampler u_sampler (
        .clk(clk), .rst_n(rst_n), .sam_cancel(cancel),
        .sam_cmd_valid(rst_n && !cancel && (state == SAM_CMD)),
        .sam_cmd_ready(sam_cmd_ready), .sam_op(sampler_op), .sam_level(level),
        .sam_seed(sampler_seed), .sam_nonce(sampler_nonce),
        .sam_m_valid(sam_m_valid), .sam_m_ready(rst_n && !cancel && (state == SAM_OUT)),
        .sam_m_coeff(sam_m_coeff), .sam_m_index(sam_m_index), .sam_m_last(sam_m_last),
        .sam_done_valid(sam_done_valid), .sam_done_ready(rst_n && !cancel && (state == SAM_DONE)),
        .sam_error(sam_error)
    );
    wire mont_a_ready, mont_m_valid;
    wire [22:0] mont_m;
    reg arithmetic_flush;
    rivet_h5_montgomery u_product (
        .clk(clk), .rst_n(rst_n && !arithmetic_flush),
        .a_valid(rst_n && !cancel && ((state == PROD_SEND) || (state == CONV_SEND))),
        .a_ready(mont_a_ready),
        .a((state == CONV_SEND) ? product_mid : prod_a_q),
        .b((state == CONV_SEND) ? 23'd2365951 : prod_b_q),
        .m_valid(mont_m_valid),
        .m_ready(rst_n && !cancel && ((state == PROD_RESULT) || (state == CONV_RESULT))),
        .m(mont_m)
    );
    wire hint_ready, w_valid;
    wire [5:0] w;
    rivet_h5_usehint u_usehint (
        .clk(clk), .rst_n(rst_n), .clear(cancel),
        .a_valid(rst_n && !cancel && (state == W_SEND)), .a_ready(hint_ready),
        .a(scratch_q), .hint(hint_q), .level44(level == 0),
        .w_valid(w_valid), .w_ready(rst_n && !cancel && (state == W_RESULT)), .w(w)
    );

    (* ramstyle="M20K", nomem2reg *) reg [22:0] scratch [0:255];
    (* ramstyle="M20K", nomem2reg *) reg [22:0] zhat [0:1791];
    (* ramstyle="M20K", nomem2reg *) reg [22:0] chat [0:255];
    (* ramstyle="M20K", nomem2reg *) reg [22:0] t1hat [0:255];
    (* ramstyle="M20K", nomem2reg *) reg [22:0] accum [0:255];
    (* ramstyle="M20K", nomem2reg *) reg hints [0:2047];
    wire [23:0] acc_sum = {1'b0,accum_q}+{1'b0,product_normal};
    wire [23:0] acc_reduced = (acc_sum >= {1'b0,Q}) ? acc_sum-{1'b0,Q} : acc_sum;
    wire [23:0] acc_difference = (accum_q >= product_normal) ?
        {1'b0,accum_q}-{1'b0,product_normal} :
        {1'b0,accum_q}+{1'b0,Q}-{1'b0,product_normal};
    wire hint_index_legal = first_hint || (sig_byte > previous_hint);
    always @(posedge clk) begin
        if (rst_n && !cancel) begin
            if ((state == Z_FIELD) && (z_magnitude < norm_limit))
                scratch[coeff_index] <= z_coeff;
            if (state == T1_FIELD) scratch[coeff_index] <= {decode_bits[9:0],13'd0};
            if ((state == SAM_OUT) && sam_m_valid) scratch[sam_m_index] <= sam_m_coeff;
            if ((state == N_OUT) && n_m_valid) begin
                case (ntt_task)
                    NT_Z: zhat[{z_poly,n_m_index}] <= n_m_coeff;
                    NT_C: chat[n_m_index] <= n_m_coeff;
                    NT_T1: t1hat[n_m_index] <= n_m_coeff;
                    NT_ACC: scratch[n_m_index] <= n_m_coeff;
                endcase
            end
            if (state == N_READ) begin
                if (ntt_task == NT_ACC) accum_q <= accum[ntt_index];
                else scratch_q <= scratch[ntt_index];
            end
            if (state == ROW_CLEAR) accum[coeff_index] <= 0;
            if (state == PROD_READ) begin
                if (subtract_product) begin
                    prod_a_q <= t1hat[coeff_index]; prod_b_q <= chat[coeff_index];
                end else begin
                    prod_a_q <= scratch[coeff_index]; prod_b_q <= zhat[{col,coeff_index}];
                end
                accum_q <= accum[coeff_index];
            end
            if (state == ACC_WRITE)
                accum[coeff_index] <= subtract_product ? acc_difference[22:0] : acc_reduced[22:0];
            if (state == H_ZERO) hints[hint_clear_index[10:0]] <= 0;
            if ((state == H_IDX_CHECK) && hint_index_legal)
                hints[{hint_row[2:0],sig_byte}] <= 1;
            if (state == W_READ) begin
                scratch_q <= scratch[coeff_index]; hint_q <= hints[{row,coeff_index}];
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE; hash_return <= 0; ntt_return <= 0; sampler_return <= 0;
            level <= 0; key_level <= 0; rx_kind <= 0; ntt_task <= 0;
            locked <= 0; auth <= 0; mismatch <= 0; status <= 0;
            context_length <= 0; message_length <= 0; rx_length <= 0; rx_received <= 0;
            rx_word <= 0; rx_beat_bytes <= 0; rx_byte_index <= 0; rx_last <= 0;
            tr <= 0; mu <= 0; rho <= 0; challenge <= 0; reconstructed_challenge <= 0;
            sig_cursor <= 0; pk_cursor <= 0; hash_index <= 0;
            z_poly <= 0; col <= 0; row <= 0; coeff_index <= 0; ntt_index <= 0;
            decode_bits <= 0; decode_count <= 0; hint_clear_index <= 0;
            hint_row <= 0; hint_cursor <= 0; previous_endpoint <= 0; previous_hint <= 0;
            first_hint <= 0; sampler_op <= 0; sampler_seed <= 0; sampler_nonce <= 0;
            subtract_product <= 0; product_mid <= 0; product_normal <= 0;
            w_bits <= 0; w_count <= 0; arithmetic_flush <= 0;
        end else if (cancel) begin
            state <= IDLE; auth <= 0; status <= 0; arithmetic_flush <= 1;
            mu <= 0; challenge <= 0; reconstructed_challenge <= 0;
            decode_bits <= 0; decode_count <= 0; w_bits <= 0; w_count <= 0;
            rx_word <= 0; rx_received <= 0;
        end else begin
            arithmetic_flush <= 0;
            case (state)
                IDLE: if (pq_cmd_valid && pq_cmd_ready) begin
                    auth <= 0; status <= 0; mismatch <= 0;
                    reconstructed_challenge <= 0;
                    if ((pq_cmd_op == 3) || (pq_level == 3)) begin
                        status <= 1; state <= RESULT;
                    end else if ((pq_cmd_op == 0) && locked) begin
                        status <= 6; state <= RESULT;
                    end else if ((pq_cmd_op == 1) && (!locked || (pq_level != key_level))) begin
                        status <= 1; state <= RESULT;
                    end else begin
                        level <= pq_level; context_length <= pq_ctx_bytes;
                        message_length <= pq_message_bytes; rx_received <= 0;
                        if (pq_cmd_op == 0) begin
                            rx_kind <= 0;
                            case (pq_level)
                                0: rx_length <= 1312;
                                1: rx_length <= 1952;
                                default: rx_length <= 2592;
                            endcase
                        end else begin
                            rx_kind <= 1;
                            case (pq_level)
                                0: rx_length <= 2420;
                                1: rx_length <= 3309;
                                default: rx_length <= 4627;
                            endcase
                        end
                        state <= RX;
                    end
                end
                RX: if (pq_s_valid && pq_s_ready) begin
                    if (!framing_legal) begin status <= 2; state <= RESULT; end
                    else begin
                        rx_received <= proposed_received;
                        if (rx_kind == 0) begin
                            if (pq_s_last) begin
                                pk_cursor <= 0; hash_index <= 0; tr <= 0; rho <= 0;
                                hash_return <= PK_READ; state <= H_CLEAR;
                            end
                        end else if (rx_kind == 1) begin
                            if (pq_s_last) begin
                                sig_cursor <= 0; challenge <= 0; state <= C_READ;
                            end
                        end else if (beat_bytes == 0) begin
                            if (rx_kind == 2) begin
                                rx_kind <= 3; rx_length <= {1'b0,message_length};
                                rx_received <= 0;
                            end else begin hash_index <= 0; mu <= 0; state <= MU_OUT; end
                        end else begin
                            rx_word <= pq_s_data; rx_last <= pq_s_last;
                            rx_beat_bytes <= beat_bytes; rx_byte_index <= 0;
                            state <= RX_DRAIN;
                        end
                    end
                end
                RX_DRAIN: if (hash_s_ready) begin
                    if (rx_byte_index == rx_beat_bytes-1'b1) begin
                        rx_word <= 0;
                        if (rx_last && (rx_kind == 2)) begin
                            rx_kind <= 3; rx_length <= {1'b0,message_length};
                            rx_received <= 0; state <= RX;
                        end else if (rx_last) begin
                            hash_index <= 0; mu <= 0; state <= MU_OUT;
                        end else state <= RX;
                    end else rx_byte_index <= rx_byte_index+1'b1;
                end
                H_CLEAR: state <= H_CMD;
                H_CMD: if (hash_cmd_ready) state <= hash_return;
                PK_READ: state <= PK_WAIT;
                PK_WAIT: state <= PK_SEND;
                PK_SEND: if (hash_s_ready) begin
                    if (pk_cursor < 32) rho[8*pk_cursor +: 8] <= pk_byte;
                    if (pk_cursor == pk_bytes-1'b1) begin hash_index <= 0; state <= TR_OUT; end
                    else begin pk_cursor <= pk_cursor+1'b1; state <= PK_READ; end
                end
                TR_OUT: if (hash_m_valid) begin
                    tr[8*hash_index +: 8] <= hash_m_data;
                    if (hash_index == 63) begin
                        locked <= 1; key_level <= level; status <= 0; auth <= 0; state <= RESULT;
                    end else hash_index <= hash_index+1'b1;
                end
                C_READ: state <= C_WAIT;
                C_WAIT: state <= C_STORE;
                C_STORE: begin
                    challenge[8*sig_cursor +: 8] <= sig_byte;
                    if (sig_cursor == {6'd0,c_bytes}-1'b1) state <= Z_INIT;
                    else begin sig_cursor <= sig_cursor+1'b1; state <= C_READ; end
                end
                Z_INIT: begin
                    sig_cursor <= {6'd0,c_bytes}; coeff_index <= 0; z_poly <= 0;
                    decode_bits <= 0; decode_count <= 0; state <= Z_NEED;
                end
                Z_NEED: begin
                    if (decode_count >= z_width) state <= Z_FIELD;
                    else state <= Z_READ;
                end
                Z_READ: state <= Z_WAIT;
                Z_WAIT: state <= Z_PACK;
                Z_PACK: begin
                    decode_bits <= decode_bits | ({32'd0,sig_byte} << decode_count);
                    decode_count <= decode_count+6'd8; sig_cursor <= sig_cursor+1'b1;
                    state <= Z_NEED;
                end
                Z_FIELD: begin
                    if (z_magnitude >= norm_limit) begin status <= 4; state <= RESULT; end
                    else begin
                        decode_bits <= decode_bits >> z_width;
                        decode_count <= decode_count-z_width;
                        if (coeff_index == 255) begin
                            ntt_task <= NT_Z; ntt_return <= Z_NEXT; ntt_index <= 0; state <= N_CMD;
                        end else begin coeff_index <= coeff_index+1'b1; state <= Z_NEED; end
                    end
                end
                Z_NEXT: begin
                    if ({1'b0,z_poly} == l-1'b1) begin
                        hint_clear_index <= 0; hint_row <= 0;
                        previous_endpoint <= 0; state <= H_ZERO;
                    end else begin
                        z_poly <= z_poly+1'b1; coeff_index <= 0; state <= Z_NEED;
                    end
                end
                N_CMD: if (n_cmd_ready) begin ntt_index <= 0; state <= N_READ; end
                N_READ: state <= N_WAIT;
                N_WAIT: state <= N_SEND;
                N_SEND: if (n_s_ready) begin
                    if (ntt_index == 255) state <= N_OUT;
                    else begin ntt_index <= ntt_index+1'b1; state <= N_READ; end
                end
                N_OUT: if (n_m_valid && n_m_last) state <= N_DONE;
                N_DONE: if (n_done_valid) begin
                    if (n_error != 0) begin status <= 3; state <= RESULT; end
                    else state <= ntt_return;
                end
                H_ZERO: begin
                    if (hint_clear_index == {k,8'd0}-1'b1) state <= H_END_READ;
                    else hint_clear_index <= hint_clear_index+1'b1;
                end
                H_END_READ: state <= H_END_WAIT;
                H_END_WAIT: state <= H_END_CHECK;
                H_END_CHECK: begin
                    if ((sig_byte < previous_endpoint) || (sig_byte > omega)) begin
                        status <= 3; state <= RESULT;
                    end else begin
                        endpoints[hint_row] <= sig_byte; previous_endpoint <= sig_byte;
                        if (hint_row == k-1'b1) begin
                            hint_row <= 0; hint_cursor <= 0; first_hint <= 1; state <= H_ROW;
                        end else begin hint_row <= hint_row+1'b1; state <= H_END_READ; end
                    end
                end
                H_ROW: begin
                    if (hint_cursor == endpoints[hint_row]) begin
                        if (hint_row == k-1'b1) state <= H_UNUSED;
                        else begin hint_row <= hint_row+1'b1; first_hint <= 1; end
                    end else state <= H_IDX_READ;
                end
                H_IDX_READ: state <= H_IDX_WAIT;
                H_IDX_WAIT: state <= H_IDX_CHECK;
                H_IDX_CHECK: begin
                    if (!hint_index_legal) begin status <= 3; state <= RESULT; end
                    else begin
                        previous_hint <= sig_byte; first_hint <= 0;
                        hint_cursor <= hint_cursor+1'b1; state <= H_ROW;
                    end
                end
                H_UNUSED: begin
                    if (hint_cursor == omega) state <= MU_SETUP;
                    else state <= H_UN_READ;
                end
                H_UN_READ: state <= H_UN_WAIT;
                H_UN_WAIT: state <= H_UN_CHECK;
                H_UN_CHECK: begin
                    if (sig_byte != 0) begin status <= 3; state <= RESULT; end
                    else begin hint_cursor <= hint_cursor+1'b1; state <= H_UNUSED; end
                end
                MU_SETUP: begin
                    hash_index <= 0; hash_return <= MU_PREFIX; state <= H_CLEAR;
                end
                MU_PREFIX: if (hash_s_ready) begin
                    if (hash_index == 65) begin
                        rx_kind <= 2; rx_length <= {25'd0,context_length};
                        rx_received <= 0; state <= RX;
                    end else hash_index <= hash_index+1'b1;
                end
                MU_OUT: if (hash_m_valid) begin
                    mu[8*hash_index +: 8] <= hash_m_data;
                    if (hash_index == 63) state <= C_SAMPLE;
                    else hash_index <= hash_index+1'b1;
                end
                C_SAMPLE: begin
                    sampler_op <= 4; sampler_seed <= challenge; sampler_nonce <= 0;
                    sampler_return <= C_NTT; state <= SAM_CMD;
                end
                SAM_CMD: if (sam_cmd_ready) state <= SAM_OUT;
                SAM_OUT: if (sam_m_valid && sam_m_last) state <= SAM_DONE;
                SAM_DONE: if (sam_done_valid) begin
                    if (sam_error != 0) begin status <= 1; state <= RESULT; end
                    else state <= sampler_return;
                end
                C_NTT: begin
                    ntt_task <= NT_C; ntt_return <= CHECK_SETUP; state <= N_CMD;
                end
                CHECK_SETUP: begin
                    hash_return <= CHECK_PREFIX; hash_index <= 0; row <= 0;
                    coeff_index <= 0; w_bits <= 0; w_count <= 0; state <= H_CLEAR;
                end
                CHECK_PREFIX: if (hash_s_ready) begin
                    if (hash_index == 63) begin coeff_index <= 0; state <= ROW_CLEAR; end
                    else hash_index <= hash_index+1'b1;
                end
                ROW_CLEAR: begin
                    if (coeff_index == 255) begin col <= 0; state <= MATRIX_START; end
                    else coeff_index <= coeff_index+1'b1;
                end
                MATRIX_START: begin
                    sampler_op <= 0; sampler_seed <= {256'd0,rho};
                    sampler_nonce <= {5'd0,row,5'd0,col};
                    sampler_return <= PROD_INIT; state <= SAM_CMD;
                end
                PROD_INIT: begin coeff_index <= 0; subtract_product <= 0; state <= PROD_READ; end
                PROD_READ: state <= PROD_WAIT;
                PROD_WAIT: state <= PROD_SEND;
                PROD_SEND: if (mont_a_ready) state <= PROD_RESULT;
                PROD_RESULT: if (mont_m_valid) begin product_mid <= mont_m; state <= CONV_SEND; end
                CONV_SEND: if (mont_a_ready) state <= CONV_RESULT;
                CONV_RESULT: if (mont_m_valid) begin product_normal <= mont_m; state <= ACC_WRITE; end
                ACC_WRITE: state <= PROD_NEXT;
                PROD_NEXT: begin
                    if (coeff_index == 255) begin
                        if (subtract_product) state <= INV_NTT;
                        else if ({1'b0,col} == l-1'b1) state <= T1_INIT;
                        else begin col <= col+1'b1; state <= MATRIX_START; end
                    end else begin coeff_index <= coeff_index+1'b1; state <= PROD_READ; end
                end
                T1_INIT: begin
                    pk_cursor <= 12'd32+({9'd0,row} << 8)+({9'd0,row} << 6);
                    decode_bits <= 0; decode_count <= 0; coeff_index <= 0; state <= T1_NEED;
                end
                T1_NEED: begin
                    if (decode_count >= 10) state <= T1_FIELD;
                    else state <= T1_READ;
                end
                T1_READ: state <= T1_WAIT;
                T1_WAIT: state <= T1_PACK;
                T1_PACK: begin
                    decode_bits <= decode_bits | ({32'd0,pk_byte} << decode_count);
                    decode_count <= decode_count+6'd8; pk_cursor <= pk_cursor+1'b1;
                    state <= T1_NEED;
                end
                T1_FIELD: begin
                    decode_bits <= decode_bits >> 10; decode_count <= decode_count-6'd10;
                    if (coeff_index == 255) state <= T1_NTT;
                    else begin coeff_index <= coeff_index+1'b1; state <= T1_NEED; end
                end
                T1_NTT: begin ntt_task <= NT_T1; ntt_return <= SUB_INIT; state <= N_CMD; end
                SUB_INIT: begin coeff_index <= 0; subtract_product <= 1; state <= PROD_READ; end
                INV_NTT: begin ntt_task <= NT_ACC; ntt_return <= W_INIT; state <= N_CMD; end
                W_INIT: begin coeff_index <= 0; w_bits <= 0; w_count <= 0; state <= W_READ; end
                W_READ: state <= W_WAIT;
                W_WAIT: state <= W_SEND;
                W_SEND: if (hint_ready) state <= W_RESULT;
                W_RESULT: if (w_valid) begin
                    w_bits <= w_bits | ({10'd0,w} << w_count);
                    if (level == 0) w_count <= w_count+5'd6;
                    else w_count <= w_count+5'd4;
                    if (w_count + ((level == 0) ? 5'd6 : 5'd4) >= 8) state <= W_DRAIN;
                    else state <= W_NEXT;
                end
                W_DRAIN: if (hash_s_ready) begin
                    w_bits <= w_bits >> 8; w_count <= w_count-5'd8;
                    if (w_count < 16) state <= W_NEXT;
                end
                W_NEXT: begin
                    if (coeff_index == 255) begin
                        if ({1'b0,row} == k-1'b1) begin
                            hash_index <= 0; mismatch <= 0; state <= CC_OUT;
                        end else begin row <= row+1'b1; coeff_index <= 0; state <= ROW_CLEAR; end
                    end else begin coeff_index <= coeff_index+1'b1; state <= W_READ; end
                end
                CC_OUT: if (hash_m_valid) begin
                    reconstructed_challenge[8*hash_index +: 8] <= hash_m_data;
                    mismatch <= mismatch || (hash_m_data != challenge[8*hash_index +: 8]);
                    if (hash_index == c_bytes-1'b1) begin
                        if (mismatch || (hash_m_data != challenge[8*hash_index +: 8])) begin
                            status <= 5; auth <= 0;
                        end else begin status <= 0; auth <= 1; end
                        state <= RESULT;
                    end else hash_index <= hash_index+1'b1;
                end
                RESULT: if (pq_result_ready) begin status <= 0; auth <= 0; state <= IDLE; end
                default: begin status <= 1; auth <= 0; state <= RESULT; end
            endcase
        end
    end
endmodule
