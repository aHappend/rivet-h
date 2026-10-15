`timescale 1ns/1ps
module compress_tb;
    reg clk=0, rst_n, clear=0, start=0;
    reg [511:0] block_data=0;
    reg [255:0] state_in=0;
    wire busy, done;
    wire [255:0] state_out;
    reg [255:0] expected;
    integer fd, n, i, j, count=0;
    string vectors;
    rivet_h2_compress unit_under_test(
        .clk(clk), .rst_n(rst_n), .clear(clear), .start(start),
        .block_data(block_data), .state_in(state_in),
        .busy(busy), .done(done), .state_out(state_out));

    task tick;
        begin
            #4 clk=1; #1;
            if ((^{busy,done,state_out}) === 1'bx) $fatal(1,"ASSERT_UNIT_XZ");
            #5 clk=0;
        end
    endtask
    task empty_outputs;
        begin
            if({busy,done,state_out} !== 258'd0) $fatal(1,"ASSERT_UNIT_CLEAR");
        end
    endtask
    initial begin
        rst_n=0; #1; empty_outputs();
        tick(); rst_n=1;
        if(!$value$plusargs("vectors=%s",vectors)) $fatal(1,"MISSING_UNIT_VECTORS");
        fd=$fopen(vectors,"r");
        if(!fd) $fatal(1,"OPEN_UNIT_VECTORS");
        while(!$feof(fd)) begin
            n=$fscanf(fd,"%h %h %h\n",state_in,block_data,expected);
            if(n != 3) begin
                if(!$feof(fd) || n>0) $fatal(1,"MALFORMED_UNIT_VECTOR");
            end else begin
                start=1; tick(); start=0;
                if(!busy || done) $fatal(1,"ASSERT_COMPRESS_LAUNCH");
                for(i=1;i<=64;i=i+1) begin
                    tick();
                    if(!busy || done) $fatal(1,"ASSERT_COMPRESS_ROUND_LATENCY round=%0d",i);
                end
                tick();
                if(busy || !done || state_out !== expected)
                    $fatal(1,"ASSERT_COMPRESS_FEEDFORWARD");
                tick();
                if(done || busy) $fatal(1,"ASSERT_COMPRESS_DONE_PULSE");
                count=count+1;
                $display("UNIT_COMPARE %0d",count);
            end
        end
        $fclose(fd);
        for(j=0;j<=65;j=j+1) begin
            start=1; tick(); start=0;
            for(i=0;i<j;i=i+1) tick();
            clear=1; tick(); clear=0; empty_outputs();
            for(i=0;i<70;i=i+1) begin
                tick(); empty_outputs();
            end
        end
        if(count<32) $fatal(1,"ASSERT_UNIT_COUNT");
        $display("UNIT_RESULT %0d 66",count);
        $finish;
    end
endmodule
