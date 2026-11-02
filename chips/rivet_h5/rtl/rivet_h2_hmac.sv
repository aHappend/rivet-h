module rivet_h2_hmac (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         clear,
    input  wire         begin_key,
    input  wire         restore,
    input  wire         restore_key_valid,
    input  wire [255:0] restore_inner,
    input  wire [255:0] restore_outer,
    input  wire         key_byte_valid,
    input  wire [7:0]   key_byte,
    input  wire         normalize,
    input  wire         long_key,
    input  wire [255:0] hash_digest,
    input  wire         write_inner,
    input  wire         write_outer,
    input  wire [255:0] seed_result,
    output reg          key_valid,
    output reg  [255:0] inner_seed,
    output reg  [255:0] outer_seed,
    output wire [511:0] ipad_block,
    output wire [511:0] opad_block
);
    reg [511:0] normalized_key;
    reg [6:0] retained_bytes;

    assign ipad_block = normalized_key ^ {64{8'h36}};
    assign opad_block = normalized_key ^ {64{8'h5c}};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            normalized_key <= 512'd0;
            retained_bytes <= 7'd0;
            key_valid <= 1'b0;
            inner_seed <= 256'd0;
            outer_seed <= 256'd0;
        end else if (clear || begin_key) begin
            normalized_key <= 512'd0;
            retained_bytes <= 7'd0;
            key_valid <= 1'b0;
            inner_seed <= 256'd0;
            outer_seed <= 256'd0;
        end else if (restore) begin
            normalized_key <= 512'd0;
            retained_bytes <= 7'd0;
            key_valid <= restore_key_valid;
            inner_seed <= restore_inner;
            outer_seed <= restore_outer;
        end else begin
            if (key_byte_valid && (retained_bytes < 7'd64)) begin
                normalized_key[511 - retained_bytes * 8 -: 8] <= key_byte;
                retained_bytes <= retained_bytes + 7'd1;
            end
            if (normalize && long_key)
                normalized_key <= {hash_digest, 256'd0};
            if (write_inner)
                inner_seed <= seed_result;
            if (write_outer) begin
                outer_seed <= seed_result;
                key_valid <= 1'b1;
                normalized_key <= 512'd0;
                retained_bytes <= 7'd0;
            end
        end
    end
endmodule
