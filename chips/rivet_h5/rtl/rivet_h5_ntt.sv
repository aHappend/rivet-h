module rivet_h5_ntt (
    input wire clk, rst_n,
    input wire n_cancel,
    input wire n_cmd_valid,
    output wire n_cmd_ready,
    input wire n_inverse,
    input wire n_s_valid,
    output wire n_s_ready,
    input wire [22:0] n_s_coeff,
    input wire n_s_last,
    output wire n_m_valid,
    input wire n_m_ready,
    output wire [22:0] n_m_coeff,
    output wire [7:0] n_m_index,
    output wire n_m_last,
    output wire n_done_valid,
    input wire n_done_ready,
    output wire [1:0] n_error
);
    localparam [22:0] Q=23'd8380417;
    // Byte-aligned ROM entries: R * 1753^BitRev8(k) in Z_q, k=0..255.
    localparam [6143:0] ZETAS=6144'h1e29ce72f6b7155e683c15ca6b16e07f234f3bcf2c776a5149c5aa189c2a70f80602cc935cfd0a7973de5dc1b0530765455fdc7be5db6f0634666e991d2668645caf1a4cd0795d4607340e1a35e770fbf521c4f7041dc03b011535c53951813d646c3e47816819379a0c5ca52dfd7118aa08027c1c4f4cbf6d73a802d4bb3368981ddd987d5c902573b7251d8b612659463e200910d8470c1358711c63b158665ff954aa0d77993533f8cf221de80bdbe716e4056ae5ae5905791d40996c595461ed6f3272831406c778fde56a0d304d3e3f12e11b6b88bf6fd6a71d0b4b1c853f52308a49bb912838911314be466519185a4625f0511309843de11c134d71585a3b2911992b5ee50319241a7cc74ce03c3472e73eb01b5aad4204610c0539194901c374259377dcd749997e30ef861f0084503af775e02277e6fd7f370567428b078f830c7f5a0de0e61c5e1a0dbe5e4f25df6d9b574682fd4a28a1359b5d6d04f12525870412f54984235a8ba0223dfb4cdf733a41f82358d433ff5a1fea933a97d948805844a79d51cea369e80373794567b0e1139e251477921413057d2ae15b1c94639ff73036c249a80902e46c6bc8090b98a17ca7e024756c4e49c11939487fbe7f470bcb3c675a0dcd446f16bf00ad002f458807c417040af04cdbea6a0c631c45631495d47a0bde6be9f87f863c6d211475a2835a140a799a6e47844c5297a4296e9f20c63870de863410f201efca4870e14fb2af4f3281709cf74190731d97726caf7667afbc2135c73509ee69b65e51781a47c1d0688c8243e6e6552f2e1f9d5458dc313b85343b38530e8f76081b9a0c63a838738c67745d5f361835843f458f5a357e1e66cad765f23e77a55e23d69c7b4a4e360400541e42368a96516e7d44f5863bbeaf5927d549102d66850435dec52ef4cd017620294a670445c53d32017f94231ad0354ddc996a84f844fae85f8dd75fb37c27f9686ecaa1777d9136b7886f65a50fa07029965828e5272f7a4953db0a2f9a755ff4807a64ae23e92b1bde2b071e24728129740119039e4477f5045811030064f73ffe00;
    localparam [3:0] IDLE=0, RECEIVE=1, READ_PAIR=2, READ_WAIT=3,
        BF_SEND=4, BF_WAIT=5, NEXT_PAIR=6, NORM_READ=7, NORM_WAIT=8,
        NORM_SEND=9, NORM_RESULT=10, OUT_READ=11, OUT_WAIT=12,
        OUT_SEND=13, DONE=14;
    reg [3:0] state;
    reg inverse, flush;
    reg [1:0] error_code;
    reg [7:0] input_index, j, twiddle_index, output_index;
    reg [8:0] length, group_start;
    reg [22:0] output_coeff;
    (* ramstyle="M20K", nomem2reg *) reg [22:0] poly [0:255];
    reg [22:0] ram_u, ram_v;
    wire [8:0] second_index = {1'b0,j} + length;
    wire [8:0] group_end = group_start + length - 9'd1;
    wire [9:0] next_group = {1'b0,group_start} + {length,1'b0};
    wire [22:0] rom_zeta = ZETAS[24*twiddle_index +: 23];
    wire [22:0] selected_zeta = inverse ? Q-rom_zeta : rom_zeta;
    wire bf_ready, bf_valid;
    wire [22:0] bf_a, bf_b;
    wire normalizing = (state == NORM_SEND) || (state == NORM_RESULT);
    wire bf_dispatch = (state == BF_SEND) || (state == NORM_SEND);
    wire bf_retire = (state == BF_WAIT) || (state == NORM_RESULT);
    assign n_cmd_ready = rst_n && !n_cancel && (state == IDLE);
    assign n_s_ready = rst_n && !n_cancel && (state == RECEIVE);
    assign n_m_valid = rst_n && !n_cancel && (state == OUT_SEND);
    assign n_m_coeff = n_m_valid ? output_coeff : 23'd0;
    assign n_m_index = n_m_valid ? output_index : 8'd0;
    assign n_m_last = n_m_valid && (output_index == 255);
    assign n_done_valid = rst_n && !n_cancel && (state == DONE);
    assign n_error = n_done_valid ? error_code : 2'd0;

    rivet_h5_butterfly u_butterfly (
        .clk(clk), .rst_n(rst_n && !flush),
        .b_valid(rst_n && !n_cancel && bf_dispatch), .b_ready(bf_ready),
        .b_inverse(inverse && !normalizing),
        .b_u(normalizing ? 23'd0 : ram_u), .b_v(normalizing ? ram_u : ram_v),
        .b_zeta(normalizing ? 23'd16382 : selected_zeta),
        .b_m_valid(bf_valid),
        .b_m_ready(rst_n && !n_cancel && bf_retire),
        .b_a(bf_a), .b_b(bf_b)
    );
    always @(posedge clk) begin
        if (rst_n && !n_cancel) begin
            if (n_s_valid && n_s_ready && (n_s_coeff < Q))
                poly[input_index] <= n_s_coeff;
            if (state == READ_PAIR) begin
                ram_u <= poly[j]; ram_v <= poly[second_index[7:0]];
            end
            if (state == NORM_READ) ram_u <= poly[output_index];
            if (state == OUT_READ) ram_u <= poly[output_index];
            if ((state == BF_WAIT) && bf_valid) begin
                poly[j] <= bf_a; poly[second_index[7:0]] <= bf_b;
            end
            if ((state == NORM_RESULT) && bf_valid)
                poly[output_index] <= bf_a;
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE; inverse <= 0; flush <= 0; error_code <= 0;
            input_index <= 0; j <= 0; twiddle_index <= 0;
            output_index <= 0; length <= 0; group_start <= 0;
            output_coeff <= 0;
        end else if (n_cancel) begin
            state <= IDLE; flush <= 1; error_code <= 0; output_coeff <= 0;
            input_index <= 0; j <= 0; output_index <= 0;
        end else begin
            flush <= 0;
            case (state)
                IDLE: if (n_cmd_valid && n_cmd_ready) begin
                    inverse <= n_inverse; input_index <= 0; error_code <= 0;
                    state <= RECEIVE;
                end
                RECEIVE: if (n_s_valid && n_s_ready) begin
                    if (n_s_last != (input_index == 255)) begin
                        error_code <= 1; state <= DONE;
                    end else if (n_s_coeff >= Q) begin
                        error_code <= 2; state <= DONE;
                    end else if (input_index == 255) begin
                        length <= inverse ? 9'd1 : 9'd128;
                        twiddle_index <= inverse ? 8'd255 : 8'd1;
                        group_start <= 0; j <= 0; output_index <= 0;
                        state <= READ_PAIR;
                    end else input_index <= input_index + 1'b1;
                end
                READ_PAIR: state <= READ_WAIT;
                READ_WAIT: state <= BF_SEND;
                BF_SEND: if (bf_ready) state <= BF_WAIT;
                BF_WAIT: if (bf_valid) state <= NEXT_PAIR;
                NEXT_PAIR: begin
                    if ({1'b0,j} != group_end) begin
                        j <= j + 1'b1; state <= READ_PAIR;
                    end else if (next_group < 256) begin
                        group_start <= next_group[8:0]; j <= next_group[7:0];
                        if (inverse) twiddle_index <= twiddle_index - 1'b1;
                        else twiddle_index <= twiddle_index + 1'b1;
                        state <= READ_PAIR;
                    end else if ((!inverse && (length == 1)) ||
                                 (inverse && (length == 128))) begin
                        output_index <= 0;
                        if (inverse) state <= NORM_READ;
                        else state <= OUT_READ;
                    end else begin
                        group_start <= 0; j <= 0;
                        if (inverse) begin
                            length <= length << 1;
                            twiddle_index <= twiddle_index - 1'b1;
                        end else begin
                            length <= length >> 1;
                            twiddle_index <= twiddle_index + 1'b1;
                        end
                        state <= READ_PAIR;
                    end
                end
                NORM_READ: state <= NORM_WAIT;
                NORM_WAIT: state <= NORM_SEND;
                NORM_SEND: if (bf_ready) state <= NORM_RESULT;
                NORM_RESULT: if (bf_valid) begin
                    if (output_index == 255) begin
                        output_index <= 0; state <= OUT_READ;
                    end else begin
                        output_index <= output_index + 1'b1; state <= NORM_READ;
                    end
                end
                OUT_READ: state <= OUT_WAIT;
                OUT_WAIT: begin output_coeff <= ram_u; state <= OUT_SEND; end
                OUT_SEND: if (n_m_ready) begin
                    output_coeff <= 0;
                    if (output_index == 255) state <= DONE;
                    else begin
                        output_index <= output_index + 1'b1; state <= OUT_READ;
                    end
                end
                DONE: if (n_done_ready) begin error_code <= 0; state <= IDLE; end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
