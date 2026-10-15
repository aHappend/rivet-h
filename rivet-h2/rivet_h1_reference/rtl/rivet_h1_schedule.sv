module rivet_h1_schedule (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         load,
    input  wire         step,
    input  wire [511:0] block_data,
    input  wire [5:0]   round_index,
    output wire [31:0]  word
);
    reg [31:0] words [0:15];
    wire [31:0] sigma0 = {words[1][6:0], words[1][31:7]} ^
                        {words[1][17:0], words[1][31:18]} ^
                        (words[1] >> 3);
    wire [31:0] sigma1 = {words[14][16:0], words[14][31:17]} ^
                        {words[14][18:0], words[14][31:19]} ^
                        (words[14] >> 10);
    wire [31:0] expanded = sigma1 + words[9] + sigma0 + words[0];
    assign word = (round_index < 6'd16) ? words[round_index[3:0]] : expanded;
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1)
                words[i] <= 32'd0;
        end else if (load) begin
            for (i = 0; i < 16; i = i + 1)
                words[i] <= block_data[511 - i * 32 -: 32];
        end else if (step && round_index >= 6'd16) begin
            for (i = 0; i < 15; i = i + 1)
                words[i] <= words[i + 1];
            words[15] <= expanded;
        end
    end
endmodule
