module rivet_h4_sponge #(
    parameter integer PARTIAL_BEATS = 0
) (
    input wire clk,
    input wire rst_n,
    input wire x_cmd_valid,
    output wire x_cmd_ready,
    input wire x_cmd_op,
    input wire [1:0] x_alg,
    input wire [31:0] x_out_bytes,
    input wire x_s_valid,
    output wire x_s_ready,
    input wire [31:0] x_s_data,
    input wire [3:0] x_s_keep,
    input wire x_s_last,
    output wire x_m_valid,
    input wire x_m_ready,
    output wire [31:0] x_m_data,
    output wire [3:0] x_m_keep,
    output wire x_m_last,
    output wire x_error
);
    localparam [3:0] IDLE = 4'd0, RECEIVE = 4'd1, PICK = 4'd2,
        ABSORB = 4'd3, SUFFIX_PICK = 4'd4, SUFFIX_WRITE = 4'd5,
        END_PICK = 4'd6, END_WRITE = 4'd7, LAUNCH = 4'd8,
        WAIT_PERMUTE = 4'd9, OUT_PICK = 4'd10, OUT_BYTE = 4'd11,
        OUT_SEND = 4'd12, FAULT = 4'd13;
    generate
        if ((PARTIAL_BEATS != 0) && (PARTIAL_BEATS != 1)) begin : g_bad_parameter
            initial $fatal(1, "PARAMETER ERROR: PARTIAL_BEATS must be 0 or 1");
        end
    endgenerate
    reg [3:0] state;
    reg [1599:0] sponge_state;
    reg [63:0] lane_word;
    reg [7:0] rate, rate_last, position;
    reg [7:0] suffix;
    reg [63:0] byte_count;
    reg [31:0] stage_data;
    reg [2:0] stage_remaining;
    reg stage_last, input_finished, permute_output;
    reg [31:0] output_remaining, output_word;
    reg [2:0] output_used;
    reg [3:0] output_keep;
    reg output_last;
    wire keccak_busy, keccak_done;
    wire [1599:0] keccak_state;
    wire command_transfer = x_cmd_valid && x_cmd_ready;
    wire cancel = command_transfer && x_cmd_op;
    assign x_cmd_ready = rst_n && (x_cmd_op || (state == IDLE));
    assign x_s_ready = rst_n && (state == RECEIVE) && !command_transfer;
    assign x_m_valid = rst_n && (state == OUT_SEND) && !cancel;
    assign x_m_data = x_m_valid ? output_word : 32'd0;
    assign x_m_keep = x_m_valid ? output_keep : 4'd0;
    assign x_m_last = x_m_valid && output_last;
    assign x_error = rst_n && (state == FAULT);

    reg [2:0] beat_bytes;
    reg legal_mask;
    always @* begin
        beat_bytes = 3'd0;
        legal_mask = 1'b0;
        case (x_s_keep)
            4'b1000: begin
                beat_bytes = 3'd1;
                legal_mask = x_s_last || (PARTIAL_BEATS == 1);
            end
            4'b1100: begin
                beat_bytes = 3'd2;
                legal_mask = x_s_last || (PARTIAL_BEATS == 1);
            end
            4'b1110: begin
                beat_bytes = 3'd3;
                legal_mask = x_s_last || (PARTIAL_BEATS == 1);
            end
            4'b1111: begin
                beat_bytes = 3'd4;
                legal_mask = 1'b1;
            end
            4'b0000: legal_mask = x_s_last &&
                ((byte_count == 64'd0) || (PARTIAL_BEATS == 1));
            default: legal_mask = 1'b0;
        endcase
    end
    wire [64:0] proposed_count = {1'b0, byte_count} + {62'd0, beat_bytes};
    wire legal_start = (x_alg == 2'd0) ? (x_out_bytes == 32'd32) :
                       (x_alg == 2'd1) ? (x_out_bytes == 32'd64) :
                                                  (x_out_bytes != 32'd0);
    wire [63:0] absorbed_lane = lane_word ^
        ({56'd0, stage_data[31:24]} << {position[2:0], 3'b000});
    wire [63:0] suffixed_lane = lane_word ^
        ({56'd0, suffix} << {position[2:0], 3'b000});
    wire [63:0] ended_lane = lane_word ^
        (64'h80 << {rate_last[2:0], 3'b000});
    wire [7:0] squeeze_byte = lane_word >> {position[2:0], 3'b000};

    rivet_h4_keccak u_keccak (
        .clk(clk), .rst_n(rst_n), .clear(cancel),
        .start((state == LAUNCH) && !cancel),
        .state_in(sponge_state), .busy(keccak_busy),
        .done(keccak_done), .state_out(keccak_state)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            sponge_state <= 1600'd0;
            lane_word <= 64'd0;
            rate <= 8'd0;
            rate_last <= 8'd0;
            position <= 8'd0;
            suffix <= 8'd0;
            byte_count <= 64'd0;
            stage_data <= 32'd0;
            stage_remaining <= 3'd0;
            stage_last <= 1'b0;
            input_finished <= 1'b0;
            permute_output <= 1'b0;
            output_remaining <= 32'd0;
            output_word <= 32'd0;
            output_used <= 3'd0;
            output_keep <= 4'd0;
            output_last <= 1'b0;
        end else if (cancel) begin
            state <= IDLE;
            sponge_state <= 1600'd0;
            lane_word <= 64'd0;
            rate <= 8'd0;
            rate_last <= 8'd0;
            position <= 8'd0;
            suffix <= 8'd0;
            byte_count <= 64'd0;
            stage_data <= 32'd0;
            stage_remaining <= 3'd0;
            stage_last <= 1'b0;
            input_finished <= 1'b0;
            permute_output <= 1'b0;
            output_remaining <= 32'd0;
            output_word <= 32'd0;
            output_used <= 3'd0;
            output_keep <= 4'd0;
            output_last <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    if (command_transfer) begin
                        sponge_state <= 1600'd0;
                        lane_word <= 64'd0;
                        position <= 8'd0;
                        byte_count <= 64'd0;
                        stage_data <= 32'd0;
                        stage_remaining <= 3'd0;
                        stage_last <= 1'b0;
                        input_finished <= 1'b0;
                        permute_output <= 1'b0;
                        output_remaining <= x_out_bytes;
                        output_word <= 32'd0;
                        output_used <= 3'd0;
                        output_keep <= 4'd0;
                        output_last <= 1'b0;
                        suffix <= x_alg[1] ? 8'h1f : 8'h06;
                        case (x_alg)
                            2'd1: begin rate <= 8'd72; rate_last <= 8'd71; end
                            2'd2: begin rate <= 8'd168; rate_last <= 8'd167; end
                            default: begin rate <= 8'd136; rate_last <= 8'd135; end
                        endcase
                        if (legal_start)
                            state <= RECEIVE;
                        else
                            state <= FAULT;
                    end
                end
                RECEIVE: begin
                    if (x_s_valid && x_s_ready) begin
                        if (!legal_mask || proposed_count[64]) begin
                            state <= FAULT;
                            output_word <= 32'd0;
                        end else begin
                            byte_count <= proposed_count[63:0];
                            stage_data <= x_s_data;
                            stage_remaining <= beat_bytes;
                            stage_last <= x_s_last;
                            if (beat_bytes == 3'd0) begin
                                input_finished <= 1'b1;
                                state <= SUFFIX_PICK;
                            end else
                                state <= PICK;
                        end
                    end
                end
                PICK: begin
                    lane_word <= sponge_state[{position[7:3], 6'b000000} +: 64];
                    state <= ABSORB;
                end
                ABSORB: begin
                    sponge_state[{position[7:3], 6'b000000} +: 64] <= absorbed_lane;
                    stage_data <= {stage_data[23:0], 8'd0};
                    stage_remaining <= stage_remaining - 3'd1;
                    if ((stage_remaining == 3'd1) && stage_last)
                        input_finished <= 1'b1;
                    if (position == rate_last) begin
                        position <= 8'd0;
                        permute_output <= 1'b0;
                        state <= LAUNCH;
                    end else begin
                        position <= position + 8'd1;
                        if (stage_remaining == 3'd1) begin
                            if (stage_last)
                                state <= SUFFIX_PICK;
                            else
                                state <= RECEIVE;
                        end else
                            state <= PICK;
                    end
                end
                SUFFIX_PICK: begin
                    lane_word <= sponge_state[{position[7:3], 6'b000000} +: 64];
                    state <= SUFFIX_WRITE;
                end
                SUFFIX_WRITE: begin
                    sponge_state[{position[7:3], 6'b000000} +: 64] <= suffixed_lane;
                    state <= END_PICK;
                end
                END_PICK: begin
                    lane_word <= sponge_state[{rate_last[7:3], 6'b000000} +: 64];
                    state <= END_WRITE;
                end
                END_WRITE: begin
                    sponge_state[{rate_last[7:3], 6'b000000} +: 64] <= ended_lane;
                    permute_output <= 1'b1;
                    position <= 8'd0;
                    state <= LAUNCH;
                end
                LAUNCH: begin
                    if (!keccak_busy)
                        state <= WAIT_PERMUTE;
                end
                WAIT_PERMUTE: begin
                    if (keccak_done) begin
                        sponge_state <= keccak_state;
                        if (permute_output)
                            state <= OUT_PICK;
                        else if (input_finished)
                            state <= SUFFIX_PICK;
                        else if (stage_remaining != 3'd0)
                            state <= PICK;
                        else
                            state <= RECEIVE;
                    end
                end
                OUT_PICK: begin
                    lane_word <= sponge_state[{position[7:3], 6'b000000} +: 64];
                    state <= OUT_BYTE;
                end
                OUT_BYTE: begin
                    output_word[31 - output_used*8 -: 8] <= squeeze_byte;
                    output_used <= output_used + 3'd1;
                    output_remaining <= output_remaining - 32'd1;
                    position <= position + 8'd1;
                    if ((output_used == 3'd3) || (output_remaining == 32'd1)) begin
                        output_last <= (output_remaining == 32'd1);
                        case (output_used)
                            3'd0: output_keep <= 4'b1000;
                            3'd1: output_keep <= 4'b1100;
                            3'd2: output_keep <= 4'b1110;
                            default: output_keep <= 4'b1111;
                        endcase
                        state <= OUT_SEND;
                    end else
                        state <= OUT_PICK;
                end
                OUT_SEND: begin
                    if (x_m_ready) begin
                        output_word <= 32'd0;
                        output_used <= 3'd0;
                        output_keep <= 4'd0;
                        if (output_last) begin
                            output_last <= 1'b0;
                            state <= IDLE;
                        end else if (position == rate) begin
                            position <= 8'd0;
                            permute_output <= 1'b1;
                            state <= LAUNCH;
                        end else
                            state <= OUT_PICK;
                    end
                end
                FAULT: state <= FAULT;
                default: state <= FAULT;
            endcase
        end
    end
endmodule
