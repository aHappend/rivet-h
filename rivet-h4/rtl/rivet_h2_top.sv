module rivet_h2_top #(
    parameter integer PARTIAL_BEATS = 0
) (
    input  wire          clk,
    input  wire          rst_n,
    input  wire          s_valid,
    output wire          s_ready,
    input  wire [31:0]   s_data,
    input  wire [3:0]    s_keep,
    input  wire          s_last,
    output wire          m_valid,
    input  wire          m_ready,
    output wire [255:0]  m_digest,
    output wire          error,
    input  wire          k_valid,
    output wire          k_ready,
    input  wire [31:0]   k_data,
    input  wire [3:0]    k_keep,
    input  wire          k_last,
    input  wire          cmd_valid,
    input  wire [2:0]    cmd_op,
    input  wire [1535:0] cmd_context,
    output wire          cmd_ready,
    output wire          ctx_valid,
    output wire [1535:0] ctx_data,
    input  wire          ctx_ready
);
    localparam [255:0] IV = {
        32'h6a09e667, 32'hbb67ae85, 32'h3c6ef372, 32'ha54ff53a,
        32'h510e527f, 32'h9b05688c, 32'h1f83d9ab, 32'h5be0cd19
    };
    localparam [63:0] SHA_LIMIT = 64'h1fff_ffff_ffff_ffff;
    localparam [63:0] HMAC_LIMIT = 64'h1fff_ffff_ffff_ffbf;
    localparam [2:0] SHA_INIT = 3'd0, KEY_LOAD = 3'd1,
                     HMAC_INIT = 3'd2, SAVE = 3'd3,
                     RESTORE = 3'd4, CANCEL = 3'd5;
    localparam [3:0] GATHER = 4'd0, PREPARE_DATA = 4'd1,
                     PREPARE_PAD = 4'd2, LAUNCH = 4'd3,
                     WAIT_BLOCK = 4'd4, PREPARE_IPAD = 4'd5,
                     OUTPUT_DIGEST = 4'd6, OUTPUT_CONTEXT = 4'd7,
                     FAULT = 4'd8;
    localparam [2:0] DATA_BLOCK = 3'd0, PAD_FIRST = 3'd1,
                     PAD_SECOND = 3'd2, IPAD_BLOCK = 3'd3,
                     OPAD_BLOCK = 3'd4, OUTER_BLOCK = 3'd5;

    generate
        if ((PARTIAL_BEATS != 0) && (PARTIAL_BEATS != 1)) begin : g_bad_parameter
            initial begin
                $fatal(1, "PARAMETER ERROR: PARTIAL_BEATS must be 0 or 1, got %0d",
                       PARTIAL_BEATS);
            end
        end
    endgenerate

    reg [3:0] state;
    reg [2:0] purpose;
    reg mode;
    reg key_loading;
    reg final_pending;
    reg needs_second;
    reg [63:0] byte_count;
    reg [255:0] chain_state;
    reg [511:0] work_block;
    reg [255:0] work_state;
    reg [255:0] digest_reg;
    reg [1535:0] context_reg;

    wire [511:0] stream_block;
    wire [6:0] used_bytes;
    wire staged;
    wire byte_fire;
    wire [7:0] byte_data;
    wire beat_end;
    wire last_pending;
    wire compressor_busy;
    wire compressor_done;
    wire [255:0] compressed_state;
    wire key_valid;
    wire [255:0] inner_seed;
    wire [255:0] outer_seed;
    wire [511:0] ipad_block;
    wire [511:0] opad_block;
    wire [1535:0] encoded_context;
    wire candidate_valid;

    wire quiescent = (state == GATHER) && !key_loading && !staged &&
                     (used_bytes < 7'd64) && !final_pending &&
                     !compressor_busy;
    assign cmd_ready = rst_n && ((cmd_op == CANCEL) || quiescent);
    wire command_transfer = cmd_valid && cmd_ready;
    wire cancel = command_transfer && (cmd_op == CANCEL);
    wire stream_available = rst_n && (state == GATHER) && !staged &&
                            (used_bytes < 7'd64) && !final_pending &&
                            !command_transfer;
    assign s_ready = stream_available && !key_loading;
    assign k_ready = stream_available && key_loading;
    assign m_valid = rst_n && (state == OUTPUT_DIGEST);
    assign ctx_valid = rst_n && (state == OUTPUT_CONTEXT);
    assign m_digest = rst_n ? digest_reg : 256'd0;
    assign ctx_data = rst_n ? context_reg : 1536'd0;
    assign error = rst_n && (state == FAULT);

    wire transfer = (s_valid && s_ready) || (k_valid && k_ready);
    wire [31:0] input_data = key_loading ? k_data : s_data;
    wire [3:0] input_keep = key_loading ? k_keep : s_keep;
    wire input_last = key_loading ? k_last : s_last;
    reg [2:0] beat_bytes;
    reg legal_mask;
    wire [63:0] length_limit = (mode && !key_loading) ? HMAC_LIMIT : SHA_LIMIT;
    wire [64:0] proposed_count = {1'b0, byte_count} + {62'd0, beat_bytes};
    wire length_overflow = proposed_count > {1'b0, length_limit};
    wire accepted_good = transfer && legal_mask && !length_overflow;

    always @* begin
        beat_bytes = 3'd0;
        legal_mask = 1'b0;
        case (input_keep)
            4'b1000: begin
                beat_bytes = 3'd1;
                legal_mask = input_last || (PARTIAL_BEATS == 1);
            end
            4'b1100: begin
                beat_bytes = 3'd2;
                legal_mask = input_last || (PARTIAL_BEATS == 1);
            end
            4'b1110: begin
                beat_bytes = 3'd3;
                legal_mask = input_last || (PARTIAL_BEATS == 1);
            end
            4'b1111: begin
                beat_bytes = 3'd4;
                legal_mask = 1'b1;
            end
            4'b0000: legal_mask = input_last &&
                                     ((byte_count == 64'd0) || (PARTIAL_BEATS == 1));
            default: begin
                beat_bytes = 3'd0;
                legal_mask = 1'b0;
            end
        endcase
    end

    wire do_sha_init = command_transfer && (cmd_op == SHA_INIT) &&
                       (byte_count == 64'd0);
    wire do_key_load = command_transfer && (cmd_op == KEY_LOAD) &&
                       (byte_count == 64'd0);
    wire do_hmac_init = command_transfer && (cmd_op == HMAC_INIT) &&
                        (byte_count == 64'd0) && key_valid;
    wire do_restore = command_transfer && (cmd_op == RESTORE) && candidate_valid;
    wire retire_digest = m_valid && m_ready;
    wire block_complete = (state == WAIT_BLOCK) && compressor_done;
    wire key_complete = block_complete && (purpose == OPAD_BLOCK);
    wire hash_complete = block_complete &&
                         ((purpose == PAD_SECOND) ||
                          ((purpose == PAD_FIRST) && !needs_second));
    wire stream_clear = cancel || do_sha_init || do_key_load || do_hmac_init ||
                        retire_digest || key_complete;
    wire [63:0] hash_bit_length =
        (byte_count + ((mode && !key_loading) ? 64'd64 : 64'd0)) << 3;
    wire [511:0] marked_block =
        stream_block | ({8'h80, 504'd0} >> (used_bytes * 8));
    wire [511:0] padded_block = (used_bytes <= 7'd55) ?
        {marked_block[511:64], hash_bit_length} : marked_block;

    rivet_h2_stream u_stream (
        .clk(clk), .rst_n(rst_n), .clear(stream_clear), .load(do_restore),
        .release_block(block_complete && (purpose == DATA_BLOCK)),
        .capture(accepted_good), .drain(state == GATHER),
        .load_buffer(cmd_context[1399:888]),
        .load_used(cmd_context[118:112]),
        .beat_data(input_data), .beat_bytes(beat_bytes), .beat_last(input_last),
        .block_data(stream_block), .used_bytes(used_bytes), .staged(staged),
        .byte_fire(byte_fire), .byte_data(byte_data), .beat_end(beat_end),
        .last_pending(last_pending)
    );

    rivet_h2_hmac u_hmac (
        .clk(clk), .rst_n(rst_n), .clear(cancel), .begin_key(do_key_load),
        .restore(do_restore), .restore_key_valid(cmd_context[41]),
        .restore_inner(cmd_context[631:376]),
        .restore_outer(cmd_context[887:632]),
        .key_byte_valid(key_loading && byte_fire), .key_byte(byte_data),
        .normalize(hash_complete && key_loading),
        .long_key(byte_count > 64'd64), .hash_digest(compressed_state),
        .write_inner(block_complete && (purpose == IPAD_BLOCK)),
        .write_outer(key_complete), .seed_result(compressed_state),
        .key_valid(key_valid), .inner_seed(inner_seed), .outer_seed(outer_seed),
        .ipad_block(ipad_block), .opad_block(opad_block)
    );

    rivet_h2_context u_context (
        .mode(mode), .key_valid(key_valid), .count(byte_count),
        .used(used_bytes), .chain(chain_state),
        .inner_seed(inner_seed), .outer_seed(outer_seed),
        .buffer_data(stream_block), .candidate(cmd_context),
        .encoded(encoded_context), .candidate_valid(candidate_valid)
    );

    rivet_h2_compress u_compress (
        .clk(clk), .rst_n(rst_n), .clear(cancel), .start(state == LAUNCH),
        .block_data(work_block), .state_in(work_state),
        .busy(compressor_busy), .done(compressor_done), .state_out(compressed_state)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= GATHER;
            purpose <= DATA_BLOCK;
            mode <= 1'b0;
            key_loading <= 1'b0;
            final_pending <= 1'b0;
            needs_second <= 1'b0;
            byte_count <= 64'd0;
            chain_state <= IV;
            work_block <= 512'd0;
            work_state <= 256'd0;
            digest_reg <= 256'd0;
            context_reg <= 1536'd0;
        end else if (cancel) begin
            state <= GATHER;
            purpose <= DATA_BLOCK;
            mode <= 1'b0;
            key_loading <= 1'b0;
            final_pending <= 1'b0;
            needs_second <= 1'b0;
            byte_count <= 64'd0;
            chain_state <= IV;
            work_block <= 512'd0;
            work_state <= 256'd0;
            digest_reg <= 256'd0;
            context_reg <= 1536'd0;
        end else begin
            case (state)
                GATHER: begin
                    if (command_transfer) begin
                        case (cmd_op)
                            SHA_INIT, KEY_LOAD, HMAC_INIT: begin
                                if ((byte_count != 64'd0) ||
                                    ((cmd_op == HMAC_INIT) && !key_valid)) begin
                                    state <= FAULT;
                                end else begin
                                    byte_count <= 64'd0;
                                    final_pending <= 1'b0;
                                    needs_second <= 1'b0;
                                    key_loading <= (cmd_op == KEY_LOAD);
                                    mode <= (cmd_op == HMAC_INIT);
                                    if (cmd_op == HMAC_INIT)
                                        chain_state <= inner_seed;
                                    else
                                        chain_state <= IV;
                                end
                            end
                            SAVE: begin
                                context_reg <= encoded_context;
                                state <= OUTPUT_CONTEXT;
                            end
                            RESTORE: begin
                                if (!candidate_valid) begin
                                    state <= FAULT;
                                end else begin
                                    mode <= cmd_context[40];
                                    byte_count <= cmd_context[111:48];
                                    chain_state <= cmd_context[375:120];
                                    final_pending <= 1'b0;
                                    needs_second <= 1'b0;
                                    key_loading <= 1'b0;
                                end
                            end
                            default: state <= FAULT;
                        endcase
                    end else if (transfer && (!legal_mask || length_overflow)) begin
                        state <= FAULT;
                    end else begin
                        if (accepted_good)
                            byte_count <= proposed_count[63:0];
                        if (beat_end && last_pending)
                            final_pending <= 1'b1;
                        if (used_bytes == 7'd64)
                            state <= PREPARE_DATA;
                        else if (final_pending && !staged)
                            state <= PREPARE_PAD;
                    end
                end
                PREPARE_DATA: begin
                    work_block <= stream_block;
                    work_state <= chain_state;
                    purpose <= DATA_BLOCK;
                    state <= LAUNCH;
                end
                PREPARE_PAD: begin
                    work_block <= padded_block;
                    work_state <= chain_state;
                    needs_second <= (used_bytes >= 7'd56);
                    purpose <= PAD_FIRST;
                    state <= LAUNCH;
                end
                LAUNCH: state <= WAIT_BLOCK;
                WAIT_BLOCK: begin
                    if (compressor_done) begin
                        case (purpose)
                            DATA_BLOCK: begin
                                chain_state <= compressed_state;
                                state <= GATHER;
                            end
                            PAD_FIRST, PAD_SECOND: begin
                                if ((purpose == PAD_FIRST) && needs_second) begin
                                    work_block <= {448'd0, hash_bit_length};
                                    work_state <= compressed_state;
                                    needs_second <= 1'b0;
                                    purpose <= PAD_SECOND;
                                    state <= LAUNCH;
                                end else if (key_loading) begin
                                    state <= PREPARE_IPAD;
                                end else if (mode) begin
                                    work_block <= {
                                        compressed_state, 8'h80, 184'd0, 64'd768
                                    };
                                    work_state <= outer_seed;
                                    purpose <= OUTER_BLOCK;
                                    state <= LAUNCH;
                                end else begin
                                    digest_reg <= compressed_state;
                                    state <= OUTPUT_DIGEST;
                                end
                            end
                            IPAD_BLOCK: begin
                                work_block <= opad_block;
                                work_state <= IV;
                                purpose <= OPAD_BLOCK;
                                state <= LAUNCH;
                            end
                            OPAD_BLOCK: begin
                                byte_count <= 64'd0;
                                chain_state <= IV;
                                key_loading <= 1'b0;
                                mode <= 1'b0;
                                final_pending <= 1'b0;
                                needs_second <= 1'b0;
                                work_block <= 512'd0;
                                work_state <= 256'd0;
                                state <= GATHER;
                            end
                            OUTER_BLOCK: begin
                                digest_reg <= compressed_state;
                                state <= OUTPUT_DIGEST;
                            end
                            default: state <= FAULT;
                        endcase
                    end
                end
                PREPARE_IPAD: begin
                    work_block <= ipad_block;
                    work_state <= IV;
                    purpose <= IPAD_BLOCK;
                    state <= LAUNCH;
                end
                OUTPUT_DIGEST: begin
                    if (m_ready) begin
                        byte_count <= 64'd0;
                        if (mode)
                            chain_state <= inner_seed;
                        else
                            chain_state <= IV;
                        final_pending <= 1'b0;
                        needs_second <= 1'b0;
                        work_block <= 512'd0;
                        work_state <= 256'd0;
                        state <= GATHER;
                    end
                end
                OUTPUT_CONTEXT: begin
                    if (ctx_ready)
                        state <= GATHER;
                end
                FAULT: state <= FAULT;
                default: state <= FAULT;
            endcase
        end
    end
endmodule
