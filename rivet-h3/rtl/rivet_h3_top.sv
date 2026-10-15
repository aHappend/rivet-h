module rivet_h3_top #(
    parameter integer PARTIAL_BEATS = 0
) (
    input wire clk,
    input wire rst_n,
    input wire s_valid,
    output wire s_ready,
    input wire [1:0] s_channel,
    input wire [31:0] s_data,
    input wire [3:0] s_keep,
    input wire s_last,
    input wire k_valid,
    output wire k_ready,
    input wire [1:0] k_channel,
    input wire [31:0] k_data,
    input wire [3:0] k_keep,
    input wire k_last,
    input wire cmd_valid,
    output wire cmd_ready,
    input wire [1:0] cmd_channel,
    input wire [2:0] cmd_op,
    input wire [2303:0] cmd_context,
    output wire m_valid,
    input wire m_ready,
    output wire [1:0] m_channel,
    output wire [1:0] m_alg,
    output wire [511:0] m_digest,
    output wire ctx_valid,
    input wire ctx_ready,
    output wire [1:0] ctx_channel,
    output wire [2303:0] ctx_data,
    output wire [3:0] error
);
    generate
        if ((PARTIAL_BEATS != 0) && (PARTIAL_BEATS != 1)) begin : g_bad_parameter
            initial $fatal(1, "PARAMETER ERROR: PARTIAL_BEATS must be 0 or 1");
        end
    endgenerate
    wire [3:0] channel_s_ready, channel_k_ready, channel_cmd_ready;
    wire [3:0] channel_m_valid, channel_ctx_valid;
    wire [1:0] channel_alg [0:3];
    wire [511:0] channel_digest [0:3];
    wire [2303:0] channel_context [0:3];
    reg digest_locked;
    reg [1:0] digest_grant;
    reg [1:0] digest_pointer;
    reg context_locked;
    reg [1:0] context_grant;
    reg [1:0] context_pointer;
    reg digest_found, context_found;
    reg [1:0] digest_choice, context_choice;
    integer offset;
    reg [1:0] digest_index, context_index;

    assign s_ready = rst_n && channel_s_ready[s_channel];
    assign k_ready = rst_n && channel_k_ready[k_channel];
    assign cmd_ready = rst_n && channel_cmd_ready[cmd_channel];
    assign m_valid = rst_n && digest_locked;
    assign m_channel = (rst_n && digest_locked) ? digest_grant : 2'd0;
    assign m_alg = (rst_n && digest_locked) ? channel_alg[digest_grant] : 2'd0;
    assign m_digest = (rst_n && digest_locked) ?
                       channel_digest[digest_grant] : 512'd0;
    assign ctx_valid = rst_n && context_locked;
    assign ctx_channel = (rst_n && context_locked) ? context_grant : 2'd0;
    assign ctx_data = (rst_n && context_locked) ?
                      channel_context[context_grant] : 2304'd0;

    genvar channel;
    generate
        for (channel = 0; channel < 4; channel = channel + 1) begin : g_channel
            rivet_h3_channel #(.PARTIAL_BEATS(PARTIAL_BEATS)) u_channel (
                .clk(clk), .rst_n(rst_n),
                .s_valid(s_valid && (s_channel == channel)),
                .s_ready(channel_s_ready[channel]), .s_data(s_data),
                .s_keep(s_keep), .s_last(s_last),
                .k_valid(k_valid && (k_channel == channel)),
                .k_ready(channel_k_ready[channel]), .k_data(k_data),
                .k_keep(k_keep), .k_last(k_last),
                .cmd_valid(cmd_valid && (cmd_channel == channel)),
                .cmd_ready(channel_cmd_ready[channel]), .cmd_op(cmd_op),
                .cmd_context(cmd_context),
                .m_valid(channel_m_valid[channel]),
                .m_ready(digest_locked && (digest_grant == channel) && m_ready),
                .m_alg(channel_alg[channel]), .m_digest(channel_digest[channel]),
                .ctx_valid(channel_ctx_valid[channel]),
                .ctx_ready(context_locked && (context_grant == channel) && ctx_ready),
                .ctx_data(channel_context[channel]), .error(error[channel])
            );
        end
    endgenerate

    always @* begin
        digest_found = 1'b0;
        context_found = 1'b0;
        digest_choice = 2'd0;
        context_choice = 2'd0;
        digest_index = 2'd0;
        context_index = 2'd0;
        for (offset = 0; offset < 4; offset = offset + 1) begin
            digest_index = digest_pointer + offset;
            context_index = context_pointer + offset;
            if (!digest_found && channel_m_valid[digest_index]) begin
                digest_found = 1'b1;
                digest_choice = digest_index;
            end
            if (!context_found && channel_ctx_valid[context_index]) begin
                context_found = 1'b1;
                context_choice = context_index;
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            digest_locked <= 1'b0;
            digest_grant <= 2'd0;
            digest_pointer <= 2'd0;
            context_locked <= 1'b0;
            context_grant <= 2'd0;
            context_pointer <= 2'd0;
        end else begin
            if (digest_locked) begin
                if (m_ready) begin
                    digest_locked <= 1'b0;
                    digest_pointer <= digest_grant + 2'd1;
                end
            end else if (digest_found) begin
                digest_locked <= 1'b1;
                digest_grant <= digest_choice;
            end
            if (context_locked) begin
                if (ctx_ready) begin
                    context_locked <= 1'b0;
                    context_pointer <= context_grant + 2'd1;
                end
            end else if (context_found) begin
                context_locked <= 1'b1;
                context_grant <= context_choice;
            end
        end
    end
endmodule
