module rivet_h3_sha512 #(
    parameter integer PARTIAL_BEATS = 0
) (
    input wire clk,
    input wire rst_n,
    input wire clear,
    input wire init,
    input wire restore,
    input wire save,
    input wire [2047:0] candidate,
    output reg candidate_valid,
    output wire quiescent,
    output wire empty,
    input wire s_valid,
    output wire s_ready,
    input wire [31:0] s_data,
    input wire [3:0] s_keep,
    input wire s_last,
    output wire m_valid,
    input wire m_ready,
    output wire [511:0] m_digest,
    output wire ctx_valid,
    input wire ctx_ready,
    output wire [2047:0] ctx_data,
    output wire error
);
    localparam [511:0] IV = {
        64'h6a09e667f3bcc908, 64'hbb67ae8584caa73b,
        64'h3c6ef372fe94f82b, 64'ha54ff53a5f1d36f1,
        64'h510e527fade682d1, 64'h9b05688c2b3e6c1f,
        64'h1f83d9abfb41bd6b, 64'h5be0cd19137e2179
    };
    localparam [127:0] LENGTH_LIMIT = 128'h1fff_ffff_ffff_ffff_ffff_ffff_ffff_ffff;
    localparam [3:0] GATHER = 4'd0, PREPARE_DATA = 4'd1,
                     PREPARE_PAD = 4'd2, LAUNCH = 4'd3,
                     WAIT_BLOCK = 4'd4, OUTPUT_DIGEST = 4'd5,
                     OUTPUT_CONTEXT = 4'd6, FAULT = 4'd7;
    localparam [1:0] DATA_BLOCK = 2'd0, PAD_FIRST = 2'd1, PAD_SECOND = 2'd2;

    generate
        if ((PARTIAL_BEATS != 0) && (PARTIAL_BEATS != 1)) begin : g_bad_parameter
            initial $fatal(1, "PARAMETER ERROR: PARTIAL_BEATS must be 0 or 1");
        end
    endgenerate

    reg [3:0] state;
    reg [1:0] purpose;
    reg [127:0] byte_count;
    reg [511:0] chain_state;
    reg [1023:0] buffer_data;
    reg [7:0] used_bytes;
    reg staged;
    reg [31:0] stage_data;
    reg [2:0] remaining;
    reg stage_last;
    reg final_pending;
    reg needs_second;
    reg [1023:0] work_block;
    reg [511:0] work_state;
    reg [511:0] digest_reg;
    reg [2047:0] context_reg;
    wire compressor_busy;
    wire compressor_done;
    wire [511:0] compressed_state;

    assign quiescent = rst_n && (state == GATHER) && !staged &&
                       (used_bytes < 8'd128) && !final_pending &&
                       !compressor_busy;
    assign empty = byte_count == 128'd0;
    assign s_ready = quiescent && !clear && !init && !restore && !save;
    assign m_valid = rst_n && (state == OUTPUT_DIGEST);
    assign m_digest = rst_n ? digest_reg : 512'd0;
    assign ctx_valid = rst_n && (state == OUTPUT_CONTEXT);
    assign ctx_data = rst_n ? context_reg : 2048'd0;
    assign error = rst_n && (state == FAULT);

    reg [2:0] beat_bytes;
    reg legal_mask;
    always @* begin
        beat_bytes = 3'd0;
        legal_mask = 1'b0;
        case (s_keep)
            4'b1000: begin
                beat_bytes = 3'd1;
                legal_mask = s_last || (PARTIAL_BEATS == 1);
            end
            4'b1100: begin
                beat_bytes = 3'd2;
                legal_mask = s_last || (PARTIAL_BEATS == 1);
            end
            4'b1110: begin
                beat_bytes = 3'd3;
                legal_mask = s_last || (PARTIAL_BEATS == 1);
            end
            4'b1111: begin
                beat_bytes = 3'd4;
                legal_mask = 1'b1;
            end
            4'b0000: legal_mask = s_last &&
                                  ((byte_count == 128'd0) || (PARTIAL_BEATS == 1));
            default: legal_mask = 1'b0;
        endcase
    end
    wire [128:0] proposed_count = {1'b0, byte_count} + {126'd0, beat_bytes};
    wire length_overflow = proposed_count > {1'b0, LENGTH_LIMIT};
    wire transfer = s_valid && s_ready;
    wire byte_fire = (state == GATHER) && staged &&
                     (used_bytes < 8'd128) && (remaining != 3'd0);
    wire beat_end = (state == GATHER) && staged &&
                    (used_bytes < 8'd128) && (remaining <= 3'd1);
    wire [127:0] bit_length = byte_count << 3;
    wire [1023:0] marked_block =
        buffer_data | ({8'h80, 1016'd0} >> (used_bytes * 8));
    wire [1023:0] padded_block = (used_bytes < 8'd112) ?
        {marked_block[1023:128], bit_length} : marked_block;
    wire [2047:0] encoded_context = {
        376'd0, buffer_data, chain_state, used_bytes, byte_count
    };
    integer i;
    always @* begin
        candidate_valid = 1'b1;
        if ((candidate[2047:1672] != 376'd0) ||
            (candidate[127:0] > LENGTH_LIMIT) ||
            (candidate[135:128] > 8'd127) ||
            (candidate[135:128] != {1'b0, candidate[6:0]}))
            candidate_valid = 1'b0;
        if ((candidate[127:0] < 128'd128) &&
            (candidate[647:136] != IV))
            candidate_valid = 1'b0;
        for (i = 0; i < 128; i = i + 1) begin
            if ((i >= candidate[135:128]) &&
                (candidate[1671 - i * 8 -: 8] != 8'd0))
                candidate_valid = 1'b0;
        end
    end

    rivet_h3_sha512_compress u_compress (
        .clk(clk), .rst_n(rst_n), .clear(clear || init || restore),
        .start(state == LAUNCH), .block_data(work_block),
        .state_in(work_state), .busy(compressor_busy),
        .done(compressor_done), .state_out(compressed_state)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= GATHER;
            purpose <= DATA_BLOCK;
            byte_count <= 128'd0;
            chain_state <= IV;
            buffer_data <= 1024'd0;
            used_bytes <= 8'd0;
            staged <= 1'b0;
            stage_data <= 32'd0;
            remaining <= 3'd0;
            stage_last <= 1'b0;
            final_pending <= 1'b0;
            needs_second <= 1'b0;
            work_block <= 1024'd0;
            work_state <= 512'd0;
            digest_reg <= 512'd0;
            context_reg <= 2048'd0;
        end else if (clear || init) begin
            state <= GATHER;
            purpose <= DATA_BLOCK;
            byte_count <= 128'd0;
            chain_state <= IV;
            buffer_data <= 1024'd0;
            used_bytes <= 8'd0;
            staged <= 1'b0;
            stage_data <= 32'd0;
            remaining <= 3'd0;
            stage_last <= 1'b0;
            final_pending <= 1'b0;
            needs_second <= 1'b0;
            work_block <= 1024'd0;
            work_state <= 512'd0;
            digest_reg <= 512'd0;
            context_reg <= 2048'd0;
        end else if (restore) begin
            if (!candidate_valid) begin
                state <= FAULT;
            end else begin
                state <= GATHER;
                purpose <= DATA_BLOCK;
                byte_count <= candidate[127:0];
                chain_state <= candidate[647:136];
                buffer_data <= candidate[1671:648];
                used_bytes <= candidate[135:128];
                staged <= 1'b0;
                stage_data <= 32'd0;
                remaining <= 3'd0;
                stage_last <= 1'b0;
                final_pending <= 1'b0;
                needs_second <= 1'b0;
                work_block <= 1024'd0;
                work_state <= 512'd0;
                digest_reg <= 512'd0;
                context_reg <= 2048'd0;
            end
        end else if (save) begin
            context_reg <= encoded_context;
            state <= OUTPUT_CONTEXT;
        end else begin
            case (state)
                GATHER: begin
                    if (transfer && (!legal_mask || length_overflow)) begin
                        state <= FAULT;
                    end else begin
                        if (transfer) begin
                            byte_count <= proposed_count[127:0];
                            stage_data <= s_data;
                            remaining <= beat_bytes;
                            stage_last <= s_last;
                            staged <= 1'b1;
                        end else if (staged && (used_bytes < 8'd128)) begin
                            if (remaining != 3'd0) begin
                                stage_data <= {stage_data[23:0], 8'd0};
                                remaining <= remaining - 3'd1;
                            end
                            if (remaining <= 3'd1) begin
                                staged <= 1'b0;
                                stage_data <= 32'd0;
                                stage_last <= 1'b0;
                            end
                        end
                        if (byte_fire) begin
                            buffer_data[1023 - used_bytes * 8 -: 8] <=
                                stage_data[31:24];
                            used_bytes <= used_bytes + 8'd1;
                        end
                        if (beat_end && stage_last)
                            final_pending <= 1'b1;
                        if (used_bytes == 8'd128)
                            state <= PREPARE_DATA;
                        else if (final_pending && !staged)
                            state <= PREPARE_PAD;
                    end
                end
                PREPARE_DATA: begin
                    work_block <= buffer_data;
                    work_state <= chain_state;
                    purpose <= DATA_BLOCK;
                    state <= LAUNCH;
                end
                PREPARE_PAD: begin
                    work_block <= padded_block;
                    work_state <= chain_state;
                    purpose <= PAD_FIRST;
                    needs_second <= (used_bytes >= 8'd112);
                    state <= LAUNCH;
                end
                LAUNCH: state <= WAIT_BLOCK;
                WAIT_BLOCK: begin
                    if (compressor_done) begin
                        if (purpose == DATA_BLOCK) begin
                            chain_state <= compressed_state;
                            buffer_data <= 1024'd0;
                            used_bytes <= 8'd0;
                            state <= GATHER;
                        end else if ((purpose == PAD_FIRST) && needs_second) begin
                            work_block <= {896'd0, bit_length};
                            work_state <= compressed_state;
                            purpose <= PAD_SECOND;
                            needs_second <= 1'b0;
                            state <= LAUNCH;
                        end else begin
                            digest_reg <= compressed_state;
                            state <= OUTPUT_DIGEST;
                        end
                    end
                end
                OUTPUT_DIGEST: begin
                    if (m_ready) begin
                        state <= GATHER;
                        purpose <= DATA_BLOCK;
                        byte_count <= 128'd0;
                        chain_state <= IV;
                        buffer_data <= 1024'd0;
                        used_bytes <= 8'd0;
                        staged <= 1'b0;
                        stage_data <= 32'd0;
                        remaining <= 3'd0;
                        stage_last <= 1'b0;
                        final_pending <= 1'b0;
                        needs_second <= 1'b0;
                        work_block <= 1024'd0;
                        work_state <= 512'd0;
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
