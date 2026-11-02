module rivet_h5_xof (
    input wire clk, rst_n,
    input wire clear,
    input wire cmd_valid,
    output wire cmd_ready,
    input wire alg,
    input wire s_valid,
    output wire s_ready,
    input wire [7:0] s_data,
    input wire s_keep, s_last,
    output wire m_valid,
    input wire m_ready,
    output wire [7:0] m_data
);
    localparam [3:0] IDLE=0, ABSORB=1, PAD_SUFFIX=2, PAD_FINAL=3,
        PERM_START=4, PERM_WAIT=5, SQUEEZE=6, FAULT=7;
    reg [3:0] state;
    reg [1599:0] lanes;
    reg [7:0] rate, pos;
    reg final_pending, padded, any_input;
    wire keccak_done, keccak_busy;
    wire [1599:0] keccak_out;
    assign cmd_ready = rst_n && !clear && (state == IDLE);
    assign s_ready = rst_n && !clear && (state == ABSORB);
    assign m_valid = rst_n && !clear && (state == SQUEEZE);
    assign m_data = m_valid ? lanes[8*pos +: 8] : 8'd0;
    rivet_h4_keccak u_keccak (
        .clk(clk), .rst_n(rst_n), .clear(clear),
        .start(rst_n && !clear && (state == PERM_START)),
        .state_in(lanes), .busy(keccak_busy),
        .done(keccak_done), .state_out(keccak_out)
    );
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE; lanes <= 0; rate <= 0; pos <= 0;
            final_pending <= 0; padded <= 0; any_input <= 0;
        end else if (clear) begin
            state <= IDLE; lanes <= 0; rate <= 0; pos <= 0;
            final_pending <= 0; padded <= 0; any_input <= 0;
        end else begin
            case (state)
                IDLE: if (cmd_valid && cmd_ready) begin
                    lanes <= 0; pos <= 0; rate <= alg ? 8'd136 : 8'd168;
                    final_pending <= 0; padded <= 0; any_input <= 0;
                    state <= ABSORB;
                end
                ABSORB: if (s_valid && s_ready) begin
                    if (!s_keep) begin
                        if (s_last && !any_input) begin
                            final_pending <= 1; state <= PAD_SUFFIX;
                        end else state <= FAULT;
                    end else begin
                        lanes[8*pos +: 8] <= lanes[8*pos +: 8] ^ s_data;
                        any_input <= 1;
                        if (s_last) final_pending <= 1;
                        if (pos == rate-1'b1) begin
                            pos <= 0; state <= PERM_START;
                        end else begin
                            pos <= pos + 1'b1;
                            if (s_last) state <= PAD_SUFFIX;
                        end
                    end
                end
                PAD_SUFFIX: begin
                    lanes[8*pos +: 8] <= lanes[8*pos +: 8] ^ 8'h1f;
                    state <= PAD_FINAL;
                end
                PAD_FINAL: begin
                    lanes[8*(rate-1'b1) +: 8] <=
                        lanes[8*(rate-1'b1) +: 8] ^ 8'h80;
                    padded <= 1; pos <= 0; state <= PERM_START;
                end
                PERM_START: if (!keccak_busy) state <= PERM_WAIT;
                PERM_WAIT: if (keccak_done) begin
                    lanes <= keccak_out; pos <= 0;
                    if (padded) state <= SQUEEZE;
                    else if (final_pending) state <= PAD_SUFFIX;
                    else state <= ABSORB;
                end
                SQUEEZE: if (m_valid && m_ready) begin
                    if (pos == rate-1'b1) begin
                        pos <= 0; state <= PERM_START;
                    end else pos <= pos + 1'b1;
                end
                FAULT: state <= FAULT;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
