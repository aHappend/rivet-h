module rivet_h4_merkle #(
    parameter integer MAX_PAGE_BYTES = 4096
) (
    input wire clk,
    input wire rst_n,
    input wire root_valid,
    output wire root_ready,
    input wire [255:0] root_digest,
    output wire root_locked,
    input wire merkle_start_valid,
    output wire merkle_start_ready,
    input wire [31:0] merkle_page_bytes,
    input wire [5:0] merkle_depth,
    input wire [31:0] merkle_leaf_index,
    input wire merkle_s_valid,
    output wire merkle_s_ready,
    input wire [31:0] merkle_s_data,
    input wire [3:0] merkle_s_keep,
    input wire merkle_s_last,
    input wire proof_valid,
    output wire proof_ready,
    input wire [255:0] proof_digest,
    input wire proof_last,
    output wire merkle_result_valid,
    input wire merkle_result_ready,
    output wire merkle_auth_ok,
    output wire err_merkle_tamper,
    output wire tile_valid,
    input wire tile_ready,
    output wire [31:0] tile_data,
    output wire [3:0] tile_keep,
    output wire tile_last
);
    localparam integer PAGE_WORDS =
        ((MAX_PAGE_BYTES >= 1) && (MAX_PAGE_BYTES <= 4096)) ?
        ((MAX_PAGE_BYTES + 3) >> 2) : 1;
    localparam integer ADDRESS_BITS = (PAGE_WORDS > 1) ? $clog2(PAGE_WORDS) : 1;
    localparam [4:0] IDLE = 5'd0, LEAF_INIT = 5'd1, LEAF_PREFIX = 5'd2,
        PAGE = 5'd3, WAIT_LEAF = 5'd4, PROOF = 5'd5,
        NODE_INIT = 5'd6, NODE_PREFIX = 5'd7, NODE_WORD = 5'd8,
        WAIT_NODE = 5'd9, COMPARE_WORDS = 5'd10, COMPARE_DECIDE = 5'd11,
        REPLAY_READ = 5'd12, REPLAY_FORM = 5'd13, REPLAY_SEND = 5'd14,
        ABORT = 5'd15, RETIRE = 5'd16;
    generate
        if ((MAX_PAGE_BYTES < 1) || (MAX_PAGE_BYTES > 4096)) begin : g_bad_parameter
            initial $fatal(1, "PARAMETER ERROR: MAX_PAGE_BYTES must be 1..4096");
        end
    endgenerate
    reg [4:0] state;
    reg locked;
    reg [255:0] pinned_root;
    reg [12:0] page_length, received, replay_remaining;
    reg [5:0] depth, level;
    reg [31:0] index_shift;
    reg [ADDRESS_BITS-1:0] write_index, read_index;
    reg [255:0] current_digest;
    reg [511:0] node_pair;
    reg [3:0] node_word;
    reg [7:0] equal_words;
    reg result_pending, auth_status, tamper_status, release_eligible;
    reg [31:0] replay_data;
    reg [3:0] replay_keep;
    reg replay_last;

    (* ramstyle = "M20K", nomem2reg *) reg [31:0] page_ram [0:PAGE_WORDS-1];
    reg [31:0] ram_q;
    wire ram_read = rst_n && release_eligible && (state == REPLAY_READ);
    wire ram_write;
    always @(posedge clk) begin
        if (ram_write)
            page_ram[write_index] <= merkle_s_data;
        if (ram_read)
            ram_q <= page_ram[read_index];
    end

    assign root_ready = rst_n && !locked;
    assign root_locked = rst_n && locked;
    assign merkle_start_ready = rst_n && locked && (state == IDLE);
    assign merkle_result_valid = rst_n && result_pending;
    assign merkle_auth_ok = rst_n && auth_status;
    assign err_merkle_tamper = rst_n && tamper_status;
    assign tile_valid = rst_n && release_eligible && (state == REPLAY_SEND);
    assign tile_data = tile_valid ? replay_data : 32'd0;
    assign tile_keep = tile_valid ? replay_keep : 4'd0;
    assign tile_last = tile_valid && replay_last;

    reg [2:0] beat_bytes;
    reg mask_valid;
    always @* begin
        beat_bytes = 3'd0;
        mask_valid = 1'b0;
        case (merkle_s_keep)
            4'b1000: begin beat_bytes = 3'd1; mask_valid = merkle_s_last; end
            4'b1100: begin beat_bytes = 3'd2; mask_valid = merkle_s_last; end
            4'b1110: begin beat_bytes = 3'd3; mask_valid = merkle_s_last; end
            4'b1111: begin beat_bytes = 3'd4; mask_valid = 1'b1; end
            default: mask_valid = 1'b0;
        endcase
    end
    wire [13:0] proposed_received = {1'b0, received} + {11'd0, beat_bytes};
    wire page_legal = mask_valid &&
        (proposed_received <= {1'b0, page_length}) &&
        (merkle_s_last == (proposed_received == {1'b0, page_length}));
    wire descriptor_legal = (merkle_page_bytes >= 32'd1) &&
        (merkle_page_bytes <= MAX_PAGE_BYTES) && (merkle_depth <= 6'd32) &&
        ((merkle_depth == 6'd32) || ((merkle_leaf_index >> merkle_depth) == 32'd0));

    wire hash_s_ready, hash_m_valid, hash_error, hash_cmd_ready;
    wire [255:0] hash_digest;
    reg hash_s_valid;
    reg [31:0] hash_s_data;
    reg [3:0] hash_s_keep;
    reg hash_s_last;
    wire hash_cmd_valid = rst_n &&
        ((state == LEAF_INIT) || (state == NODE_INIT) || (state == ABORT));
    wire [2:0] hash_cmd_op = (state == ABORT) ? 3'd5 : 3'd0;
    wire hash_m_ready = rst_n && ((state == WAIT_LEAF) || (state == WAIT_NODE));
    assign merkle_s_ready = rst_n && (state == PAGE) && !hash_error && hash_s_ready;
    assign proof_ready = rst_n && (state == PROOF) && !hash_error;
    assign ram_write = merkle_s_valid && merkle_s_ready && page_legal;

    always @* begin
        hash_s_valid = 1'b0;
        hash_s_data = 32'd0;
        hash_s_keep = 4'd0;
        hash_s_last = 1'b0;
        if (rst_n && !hash_error) begin
            case (state)
                LEAF_PREFIX, NODE_PREFIX: begin
                    hash_s_valid = 1'b1;
                    hash_s_data = (state == NODE_PREFIX) ? 32'h01000000 : 32'd0;
                    hash_s_keep = 4'b1000;
                end
                PAGE: begin
                    hash_s_valid = merkle_s_valid && page_legal;
                    hash_s_data = merkle_s_data;
                    hash_s_keep = merkle_s_keep;
                    hash_s_last = merkle_s_last;
                end
                NODE_WORD: begin
                    hash_s_valid = 1'b1;
                    hash_s_data = node_pair[511 - node_word*32 -: 32];
                    hash_s_keep = 4'b1111;
                    hash_s_last = (node_word == 4'd15);
                end
                default: begin end
            endcase
        end
    end

    rivet_h2_top #(.PARTIAL_BEATS(1)) u_hash (
        .clk(clk), .rst_n(rst_n), .s_valid(hash_s_valid), .s_ready(hash_s_ready),
        .s_data(hash_s_data), .s_keep(hash_s_keep), .s_last(hash_s_last),
        .m_valid(hash_m_valid), .m_ready(hash_m_ready), .m_digest(hash_digest),
        .error(hash_error), .k_valid(1'b0), .k_ready(), .k_data(32'd0),
        .k_keep(4'd0), .k_last(1'b0), .cmd_valid(hash_cmd_valid),
        .cmd_op(hash_cmd_op), .cmd_context(1536'd0), .cmd_ready(hash_cmd_ready),
        .ctx_valid(), .ctx_data(), .ctx_ready(1'b0)
    );

    integer word_index;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            locked <= 1'b0;
            pinned_root <= 256'd0;
            page_length <= 13'd0;
            received <= 13'd0;
            replay_remaining <= 13'd0;
            depth <= 6'd0;
            level <= 6'd0;
            index_shift <= 32'd0;
            write_index <= {ADDRESS_BITS{1'b0}};
            read_index <= {ADDRESS_BITS{1'b0}};
            current_digest <= 256'd0;
            node_pair <= 512'd0;
            node_word <= 4'd0;
            equal_words <= 8'd0;
            result_pending <= 1'b0;
            auth_status <= 1'b0;
            tamper_status <= 1'b0;
            release_eligible <= 1'b0;
            replay_data <= 32'd0;
            replay_keep <= 4'd0;
            replay_last <= 1'b0;
        end else begin
            if (root_valid && root_ready) begin
                pinned_root <= root_digest;
                locked <= 1'b1;
            end
            if (result_pending && merkle_result_ready)
                result_pending <= 1'b0;
            if (hash_error && (state != IDLE) && (state != ABORT) &&
                (state != RETIRE)) begin
                state <= ABORT;
                result_pending <= 1'b1;
                auth_status <= 1'b0;
                tamper_status <= 1'b1;
                release_eligible <= 1'b0;
                replay_data <= 32'd0;
                replay_keep <= 4'd0;
                replay_last <= 1'b0;
            end else begin
                case (state)
                    IDLE: begin
                        if (merkle_start_valid && merkle_start_ready) begin
                            page_length <= merkle_page_bytes[12:0];
                            depth <= merkle_depth;
                            index_shift <= merkle_leaf_index;
                            level <= 6'd0;
                            received <= 13'd0;
                            write_index <= {ADDRESS_BITS{1'b0}};
                            read_index <= {ADDRESS_BITS{1'b0}};
                            current_digest <= 256'd0;
                            node_pair <= 512'd0;
                            node_word <= 4'd0;
                            equal_words <= 8'd0;
                            result_pending <= 1'b0;
                            auth_status <= 1'b0;
                            tamper_status <= 1'b0;
                            release_eligible <= 1'b0;
                            replay_remaining <= 13'd0;
                            replay_data <= 32'd0;
                            replay_keep <= 4'd0;
                            replay_last <= 1'b0;
                            if (descriptor_legal)
                                state <= LEAF_INIT;
                            else begin
                                result_pending <= 1'b1;
                                tamper_status <= 1'b1;
                                state <= ABORT;
                            end
                        end
                    end
                    LEAF_INIT: begin
                        if (hash_cmd_ready)
                            state <= LEAF_PREFIX;
                    end
                    LEAF_PREFIX: begin
                        if (hash_s_ready)
                            state <= PAGE;
                    end
                    PAGE: begin
                        if (merkle_s_valid && merkle_s_ready) begin
                            if (!page_legal) begin
                                result_pending <= 1'b1;
                                auth_status <= 1'b0;
                                tamper_status <= 1'b1;
                                release_eligible <= 1'b0;
                                state <= ABORT;
                            end else begin
                                received <= proposed_received[12:0];
                                if (merkle_s_last)
                                    state <= WAIT_LEAF;
                                else
                                    write_index <= write_index + 1'b1;
                            end
                        end
                    end
                    WAIT_LEAF: begin
                        if (hash_m_valid) begin
                            current_digest <= hash_digest;
                            if (depth == 6'd0)
                                state <= COMPARE_WORDS;
                            else
                                state <= PROOF;
                        end
                    end
                    PROOF: begin
                        if (proof_valid && proof_ready) begin
                            if (proof_last != ((level + 6'd1) == depth)) begin
                                result_pending <= 1'b1;
                                auth_status <= 1'b0;
                                tamper_status <= 1'b1;
                                release_eligible <= 1'b0;
                                state <= ABORT;
                            end else begin
                                if (index_shift[0])
                                    node_pair <= {proof_digest, current_digest};
                                else
                                    node_pair <= {current_digest, proof_digest};
                                index_shift <= {1'b0, index_shift[31:1]};
                                node_word <= 4'd0;
                                state <= NODE_INIT;
                            end
                        end
                    end
                    NODE_INIT: begin
                        if (hash_cmd_ready)
                            state <= NODE_PREFIX;
                    end
                    NODE_PREFIX: begin
                        if (hash_s_ready)
                            state <= NODE_WORD;
                    end
                    NODE_WORD: begin
                        if (hash_s_ready) begin
                            if (node_word == 4'd15)
                                state <= WAIT_NODE;
                            else
                                node_word <= node_word + 4'd1;
                        end
                    end
                    WAIT_NODE: begin
                        if (hash_m_valid) begin
                            current_digest <= hash_digest;
                            level <= level + 6'd1;
                            if ((level + 6'd1) == depth)
                                state <= COMPARE_WORDS;
                            else
                                state <= PROOF;
                        end
                    end
                    COMPARE_WORDS: begin
                        for (word_index = 0; word_index < 8; word_index = word_index + 1)
                            equal_words[word_index] <=
                                (current_digest[word_index*32 +: 32] ==
                                 pinned_root[word_index*32 +: 32]);
                        state <= COMPARE_DECIDE;
                    end
                    COMPARE_DECIDE: begin
                        result_pending <= 1'b1;
                        if (&equal_words) begin
                            auth_status <= 1'b1;
                            tamper_status <= 1'b0;
                            release_eligible <= 1'b1;
                            replay_remaining <= page_length;
                            read_index <= {ADDRESS_BITS{1'b0}};
                            state <= REPLAY_READ;
                        end else begin
                            auth_status <= 1'b0;
                            tamper_status <= 1'b1;
                            release_eligible <= 1'b0;
                            state <= RETIRE;
                        end
                    end
                    REPLAY_READ: state <= REPLAY_FORM;
                    REPLAY_FORM: begin
                        replay_last <= (replay_remaining <= 13'd4);
                        case (replay_remaining)
                            13'd1: begin
                                replay_data <= {ram_q[31:24], 24'd0};
                                replay_keep <= 4'b1000;
                            end
                            13'd2: begin
                                replay_data <= {ram_q[31:16], 16'd0};
                                replay_keep <= 4'b1100;
                            end
                            13'd3: begin
                                replay_data <= {ram_q[31:8], 8'd0};
                                replay_keep <= 4'b1110;
                            end
                            default: begin
                                replay_data <= ram_q;
                                replay_keep <= 4'b1111;
                            end
                        endcase
                        state <= REPLAY_SEND;
                    end
                    REPLAY_SEND: begin
                        if (tile_ready) begin
                            replay_data <= 32'd0;
                            replay_keep <= 4'd0;
                            replay_last <= 1'b0;
                            if (replay_last) begin
                                release_eligible <= 1'b0;
                                state <= RETIRE;
                            end else begin
                                replay_remaining <= replay_remaining - 13'd4;
                                read_index <= read_index + 1'b1;
                                state <= REPLAY_READ;
                            end
                        end
                    end
                    ABORT: begin
                        if (hash_cmd_ready)
                            state <= RETIRE;
                    end
                    RETIRE: begin
                        if (!result_pending)
                            state <= IDLE;
                    end
                    default: begin
                        state <= ABORT;
                        result_pending <= 1'b1;
                        auth_status <= 1'b0;
                        tamper_status <= 1'b1;
                        release_eligible <= 1'b0;
                        replay_data <= 32'd0;
                        replay_keep <= 4'd0;
                        replay_last <= 1'b0;
                    end
                endcase
            end
        end
    end
endmodule
