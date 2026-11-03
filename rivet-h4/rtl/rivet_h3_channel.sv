module rivet_h3_channel #(
    parameter integer PARTIAL_BEATS = 0
) (
    input wire clk,
    input wire rst_n,
    input wire s_valid,
    output wire s_ready,
    input wire [31:0] s_data,
    input wire [3:0] s_keep,
    input wire s_last,
    input wire k_valid,
    output wire k_ready,
    input wire [31:0] k_data,
    input wire [3:0] k_keep,
    input wire k_last,
    input wire cmd_valid,
    output wire cmd_ready,
    input wire [2:0] cmd_op,
    input wire [2303:0] cmd_context,
    output wire m_valid,
    input wire m_ready,
    output wire [1:0] m_alg,
    output wire [511:0] m_digest,
    output wire ctx_valid,
    input wire ctx_ready,
    output wire [2303:0] ctx_data,
    output wire error
);
    localparam [2:0] SHA_INIT = 3'd0, KEY_LOAD = 3'd1,
                     HMAC_INIT = 3'd2, SAVE = 3'd3,
                     RESTORE = 3'd4, CANCEL = 3'd5, SHA512_INIT = 3'd6;
    reg [1:0] algorithm;
    reg local_fault;
    reg h2_nonempty;
    reg h2_cleanup;
    wire active512 = algorithm == 2'd2;
    wire h2_s_ready, h2_k_ready, h2_cmd_ready, h2_m_valid, h2_ctx_valid, h2_error;
    wire [255:0] h2_digest;
    wire [1535:0] h2_context;
    wire sha_s_ready, sha_quiescent, sha_empty, sha_m_valid, sha_ctx_valid, sha_error;
    wire [511:0] sha_digest;
    wire [2047:0] sha_context;
    wire sha_candidate_valid;
    wire legacy_context = cmd_context[2303:1536] == 768'd0;
    wire [1:0] restored_algorithm = legacy_context ?
        {1'b0, cmd_context[40]} : cmd_context[2089:2088];
    wire envelope_valid = legacy_context ||
        ((cmd_context[2303:2090] == 214'd0) &&
         (cmd_context[2079:2048] == 32'h52485633) &&
         (cmd_context[2087:2080] == 8'd1) &&
         (restored_algorithm != 2'd3) &&
         ((restored_algorithm == 2'd2) ||
          ((cmd_context[2047:1536] == 512'd0) &&
           (restored_algorithm == {1'b0, cmd_context[40]}))));
    wire restore512 = (cmd_op == RESTORE) && (restored_algorithm == 2'd2);
    wire target512 = (cmd_op == SHA512_INIT) || restore512;
    wire is_init = (cmd_op == SHA_INIT) || (cmd_op == KEY_LOAD) ||
                   (cmd_op == HMAC_INIT) || (cmd_op == SHA512_INIT);
    wire nonempty = active512 ? !sha_empty : h2_nonempty;
    wire pending_response = active512 ? (sha_m_valid || sha_ctx_valid) :
                                                       (h2_m_valid || h2_ctx_valid);
    wire faulted = local_fault || (active512 ? sha_error : h2_error);
    assign error = rst_n && faulted;
    assign cmd_ready = rst_n && ((cmd_op == CANCEL) ? !pending_response :
        (!faulted && !h2_cleanup && (active512 ? sha_quiescent : h2_cmd_ready)));
    wire command_transfer = cmd_valid && cmd_ready;
    wire cancel = command_transfer && (cmd_op == CANCEL);
    wire command_fault = (cmd_op == 3'd7) ||
                         (is_init && nonempty) ||
                         ((cmd_op == RESTORE) &&
                          (!envelope_valid || (restore512 && !sha_candidate_valid)));
    wire good_command = command_transfer && !command_fault;
    wire h2_command = good_command &&
        ((cmd_op == CANCEL) ||
         (!target512 && (!active512 || (cmd_op != SAVE))));
    // Entry uses the parent's SAVE readiness as a pure quiescence probe.
    // The following edge clears inactive H2 state, including cached keys.
    wire [2:0] h2_op = h2_cleanup ? CANCEL : (target512 ? SAVE : cmd_op);

    assign s_ready = rst_n && !faulted && !command_transfer &&
                     (active512 ? sha_s_ready : h2_s_ready);
    assign k_ready = rst_n && !faulted && !command_transfer &&
                     !active512 && h2_k_ready;
    assign m_valid = rst_n && !faulted && (active512 ? sha_m_valid : h2_m_valid);
    assign m_alg = rst_n ? algorithm : 2'd0;
    assign m_digest = !rst_n ? 512'd0 :
                      (active512 ? sha_digest : {256'd0, h2_digest});
    assign ctx_valid = rst_n && !faulted &&
                       (active512 ? sha_ctx_valid : h2_ctx_valid);
    wire [2047:0] context_payload = active512 ? sha_context : {512'd0, h2_context};
    assign ctx_data = rst_n ?
        {214'd0, algorithm, 8'd1, 32'h52485633, context_payload} : 2304'd0;

    rivet_h2_top #(.PARTIAL_BEATS(PARTIAL_BEATS)) u_h2 (
        .clk(clk), .rst_n(rst_n),
        .s_valid(s_valid && !active512 && !faulted && !command_transfer),
        .s_ready(h2_s_ready), .s_data(s_data), .s_keep(s_keep), .s_last(s_last),
        .m_valid(h2_m_valid), .m_ready(m_ready && !active512 && !faulted),
        .m_digest(h2_digest), .error(h2_error),
        .k_valid(k_valid && !active512 && !faulted && !command_transfer),
        .k_ready(h2_k_ready), .k_data(k_data), .k_keep(k_keep), .k_last(k_last),
        .cmd_valid(h2_command || h2_cleanup), .cmd_op(h2_op),
        .cmd_context(cmd_context[1535:0]), .cmd_ready(h2_cmd_ready),
        .ctx_valid(h2_ctx_valid), .ctx_data(h2_context),
        .ctx_ready(ctx_ready && !active512 && !faulted)
    );

    rivet_h3_sha512 #(.PARTIAL_BEATS(PARTIAL_BEATS)) u_sha512 (
        .clk(clk), .rst_n(rst_n),
        .clear(cancel || (good_command && !target512 &&
                         ((cmd_op == RESTORE) || is_init))),
        .init(good_command && (cmd_op == SHA512_INIT)),
        .restore(good_command && restore512),
        .save(good_command && active512 && (cmd_op == SAVE)),
        .candidate(cmd_context[2047:0]), .candidate_valid(sha_candidate_valid),
        .quiescent(sha_quiescent), .empty(sha_empty),
        .s_valid(s_valid && active512 && !faulted && !command_transfer),
        .s_ready(sha_s_ready), .s_data(s_data), .s_keep(s_keep), .s_last(s_last),
        .m_valid(sha_m_valid), .m_ready(m_ready && active512 && !faulted),
        .m_digest(sha_digest), .ctx_valid(sha_ctx_valid),
        .ctx_ready(ctx_ready && active512 && !faulted), .ctx_data(sha_context),
        .error(sha_error)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            algorithm <= 2'd0;
            local_fault <= 1'b0;
            h2_nonempty <= 1'b0;
            h2_cleanup <= 1'b0;
        end else if (cancel) begin
            algorithm <= 2'd0;
            local_fault <= 1'b0;
            h2_nonempty <= 1'b0;
            h2_cleanup <= 1'b0;
        end else begin
            h2_cleanup <= 1'b0;
            if (command_transfer) begin
                if (command_fault) begin
                    local_fault <= 1'b1;
                end else begin
                    case (cmd_op)
                        SHA_INIT, KEY_LOAD: begin
                            algorithm <= 2'd0;
                            h2_nonempty <= 1'b0;
                        end
                        HMAC_INIT: begin
                            algorithm <= 2'd1;
                            h2_nonempty <= 1'b0;
                        end
                        SHA512_INIT: begin
                            algorithm <= 2'd2;
                            h2_nonempty <= 1'b0;
                            h2_cleanup <= !active512;
                        end
                        RESTORE: begin
                            algorithm <= restored_algorithm;
                            h2_nonempty <= !restore512 &&
                                           (cmd_context[111:48] != 64'd0);
                            h2_cleanup <= restore512 && !active512;
                        end
                        default: begin end
                    endcase
                end
            end else if (!active512) begin
                if (m_valid && m_ready)
                    h2_nonempty <= 1'b0;
                else if (s_valid && s_ready && (s_keep != 4'd0))
                    h2_nonempty <= 1'b1;
            end
        end
    end
endmodule
