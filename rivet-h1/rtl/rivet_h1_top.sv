module rivet_h1_top (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         s_valid,
    output wire         s_ready,
    input  wire [31:0]  s_data,
    input  wire [3:0]   s_keep,
    input  wire         s_last,
    output wire         m_valid,
    input  wire         m_ready,
    output wire [255:0] m_digest,
    output wire         error
);
    localparam [255:0] INITIAL_STATE = {
        32'h6a09e667, 32'hbb67ae85, 32'h3c6ef372, 32'ha54ff53a,
        32'h510e527f, 32'h9b05688c, 32'h1f83d9ab, 32'h5be0cd19
    };
    localparam [2:0] GATHER = 3'd0, PREPARE = 3'd1, LAUNCH = 3'd2,
                     WAIT_BLOCK = 3'd3, OUTPUT_DIGEST = 3'd4, FAULT = 3'd5;
    reg [2:0] state;
    reg final_block;
    reg error_reg;
    reg [255:0] chain_state;
    reg [255:0] digest_reg;
    reg [2:0] beat_bytes;
    reg legal_mask;
    wire [63:0] byte_count;
    wire [63:0] next_byte_count;
    wire length_overflow;
    wire [511:0] block_data;
    wire [6:0] used_bytes;
    wire needs_second;
    wire compress_done;
    wire compress_busy;
    wire [255:0] compressed_state;

    assign s_ready = rst_n && !error_reg && (state == GATHER);
    assign m_valid = rst_n && !error_reg && (state == OUTPUT_DIGEST);
    assign m_digest = rst_n ? digest_reg : 256'd0;
    assign error = rst_n && error_reg;
    wire transfer = s_valid && s_ready;
    wire retire = m_valid && m_ready;
    wire accepted_good = transfer && legal_mask && !length_overflow;
    wire consume_block = (state == WAIT_BLOCK) && compress_done;
    wire second_block = consume_block && final_block && needs_second;

    always @* begin
        beat_bytes = 3'd0;
        legal_mask = 1'b0;
        case (s_keep)
            4'b1000: begin beat_bytes = 3'd1; legal_mask = s_last; end
            4'b1100: begin beat_bytes = 3'd2; legal_mask = s_last; end
            4'b1110: begin beat_bytes = 3'd3; legal_mask = s_last; end
            4'b1111: begin beat_bytes = 3'd4; legal_mask = 1'b1; end
            4'b0000: legal_mask = s_last && (byte_count == 64'd0);
            default: begin beat_bytes = 3'd0; legal_mask = 1'b0; end
        endcase
    end

    rivet_h1_length u_length (
        .clk(clk), .rst_n(rst_n), .clear(retire), .accept(accepted_good),
        .beat_bytes(beat_bytes), .byte_count(byte_count),
        .next_byte_count(next_byte_count), .overflow(length_overflow)
    );
    rivet_h1_pad u_pad (
        .clk(clk), .rst_n(rst_n), .clear(retire), .append(accepted_good),
        .beat_data(s_data), .beat_bytes(beat_bytes),
        .prepare(state == PREPARE), .final_block(final_block),
        .prepare_second(second_block),
        .release_block(consume_block && !final_block),
        .bit_length(byte_count << 3), .block_data(block_data),
        .used_bytes(used_bytes), .needs_second(needs_second)
    );
    rivet_h1_compress u_compress (
        .clk(clk), .rst_n(rst_n), .start(state == LAUNCH),
        .block_data(block_data), .state_in(chain_state),
        .busy(compress_busy), .done(compress_done), .state_out(compressed_state)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= GATHER;
            final_block <= 1'b0;
            error_reg <= 1'b0;
            chain_state <= INITIAL_STATE;
            digest_reg <= 256'd0;
        end else begin
            case (state)
                GATHER: begin
                    if (transfer) begin
                        if (!legal_mask || length_overflow) begin
                            error_reg <= 1'b1;
                            state <= FAULT;
                        end else if (s_last ||
                                     (used_bytes + {4'd0, beat_bytes} == 7'd64)) begin
                            final_block <= s_last;
                            state <= PREPARE;
                        end
                    end
                end
                PREPARE: state <= LAUNCH;
                LAUNCH: state <= WAIT_BLOCK;
                WAIT_BLOCK: begin
                    if (compress_done) begin
                        chain_state <= compressed_state;
                        if (!final_block)
                            state <= GATHER;
                        else if (needs_second)
                            state <= LAUNCH;
                        else begin
                            digest_reg <= compressed_state;
                            state <= OUTPUT_DIGEST;
                        end
                    end
                end
                OUTPUT_DIGEST: begin
                    if (m_ready) begin
                        chain_state <= INITIAL_STATE;
                        final_block <= 1'b0;
                        state <= GATHER;
                    end
                end
                FAULT: state <= FAULT;
                default: begin
                    error_reg <= 1'b1;
                    state <= FAULT;
                end
            endcase
        end
    end
endmodule
