module rivet_h3_sha512_schedule (
    input wire clk,
    input wire rst_n,
    input wire clear,
    input wire load,
    input wire step,
    input wire [1023:0] block_data,
    input wire [6:0] round_index,
    output wire [63:0] word
);
    reg [63:0] words [0:15];
    wire [63:0] sigma0 = {words[1][0], words[1][63:1]} ^
                        {words[1][7:0], words[1][63:8]} ^
                        (words[1] >> 7);
    wire [63:0] sigma1 = {words[14][18:0], words[14][63:19]} ^
                        {words[14][60:0], words[14][63:61]} ^
                        (words[14] >> 6);
    wire [63:0] expanded = sigma1 + words[9] + sigma0 + words[0];
    assign word = (round_index < 7'd16) ? words[round_index[3:0]] : expanded;
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1)
                words[i] <= 64'd0;
        end else if (clear) begin
            for (i = 0; i < 16; i = i + 1)
                words[i] <= 64'd0;
        end else if (load) begin
            for (i = 0; i < 16; i = i + 1)
                words[i] <= block_data[1023 - i * 64 -: 64];
        end else if (step && (round_index >= 7'd16)) begin
            for (i = 0; i < 15; i = i + 1)
                words[i] <= words[i + 1];
            words[15] <= expanded;
        end
    end
endmodule
