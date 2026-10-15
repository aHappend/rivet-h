`timescale 1ns/1ps
module bridge;
    parameter integer PARTIAL = 0;
    parameter integer H1 = 0;
    reg clk = 0;
    reg rst_n;
    reg s_valid = 0, s_last = 0, m_ready = 0;
    reg [31:0] s_data = 0;
    reg [3:0] s_keep = 0;
    wire s_ready, m_valid, error;
    wire [255:0] m_digest;
    reg k_valid = 0, k_last = 0;
    reg [31:0] k_data = 0;
    reg [3:0] k_keep = 0;
    wire k_ready, cmd_ready, ctx_valid;
    reg cmd_valid = 0, ctx_ready = 0;
    reg [2:0] cmd_op = 0;
    reg [1535:0] cmd_context = 0;
    wire [1535:0] ctx_data;
    generate
        if (H1) begin : reference_top
            rivet_h1_top dut (.clk(clk), .rst_n(rst_n), .s_valid(s_valid),
                .s_ready(s_ready), .s_data(s_data), .s_keep(s_keep), .s_last(s_last),
                .m_valid(m_valid), .m_ready(m_ready), .m_digest(m_digest), .error(error));
            assign k_ready = 0;
            assign cmd_ready = 0;
            assign ctx_valid = 0;
            assign ctx_data = 0;
        end else begin : product_top
            rivet_h2_top #(.PARTIAL_BEATS(PARTIAL)) dut (
                .clk(clk), .rst_n(rst_n), .s_valid(s_valid), .s_ready(s_ready),
                .s_data(s_data), .s_keep(s_keep), .s_last(s_last), .m_valid(m_valid),
                .m_ready(m_ready), .m_digest(m_digest), .error(error),
                .k_valid(k_valid), .k_ready(k_ready), .k_data(k_data), .k_keep(k_keep),
                .k_last(k_last), .cmd_valid(cmd_valid), .cmd_op(cmd_op),
                .cmd_context(cmd_context), .cmd_ready(cmd_ready), .ctx_valid(ctx_valid),
                .ctx_data(ctx_data), .ctx_ready(ctx_ready));
        end
    endgenerate

    integer cycles = 0, comparisons = 0, sha_count = 0, hmac_count = 0;
    integer snapshots = 0, restores = 0, reset_count = 0, cancel_count = 0;
    integer last_accept = 0, first_accept = -1, accepts = 0;
    integer fd, n, op, a, b, c, i, guard;
    reg [1535:0] d;
    reg [1535:0] slots [0:15];
    reg [15:0] slot_valid = 0;
    reg old_m_stall = 0, old_c_stall = 0;
    reg [255:0] old_digest;
    reg [1535:0] old_context;
    reg was_cancel;
    reg pre_s, pre_k, pre_cmd;
    string stimulus;

    task check_reset;
        begin
            if ({s_ready,m_valid,m_digest,error,k_ready,cmd_ready,ctx_valid,ctx_data}
                !== 1798'd0) $fatal(1, "ASSERT_RESET_ZERO cycle=%0d", cycles);
        end
    endtask

    always @(posedge clk or negedge clk) begin
        if (!rst_n) check_reset();
    end

    task known_outputs;
        begin
            if ((^{s_ready,m_valid,m_digest,error,k_ready,cmd_ready,ctx_valid,ctx_data})
                === 1'bx) $fatal(1, "ASSERT_XZ cycle=%0d", cycles);
            if (!rst_n) check_reset();
        end
    endtask

    task tick;
        begin
            #3;
            known_outputs();
            was_cancel = rst_n && cmd_valid && cmd_ready && cmd_op == 5;
            pre_s = s_valid && s_ready;
            pre_k = k_valid && k_ready;
            pre_cmd = cmd_valid && cmd_ready;
            if ((pre_s && pre_k) || (pre_cmd && (pre_s || pre_k)))
                $fatal(1, "ASSERT_ARBITRATION");
            if (old_m_stall && rst_n && !was_cancel &&
                (!m_valid || m_digest !== old_digest)) $fatal(1, "ASSERT_DIGEST_STALL");
            if (old_c_stall && rst_n && !was_cancel &&
                (!ctx_valid || ctx_data !== old_context)) $fatal(1, "ASSERT_CONTEXT_STALL");
            old_m_stall = rst_n && m_valid && !m_ready && !was_cancel;
            old_c_stall = rst_n && ctx_valid && !ctx_ready && !was_cancel;
            old_digest = m_digest;
            old_context = ctx_data;
            #1 clk = 1;
            #1;
            cycles = cycles + 1;
            known_outputs();
            if (cycles > 30000000) $fatal(1, "ASSERT_CYCLE_WATCHDOG");
            if (pre_s) begin
                last_accept = cycles;
                if (first_accept < 0) first_accept = cycles;
                accepts = accepts + 1;
            end
            if (!H1 && rst_n && pre_s && !error && (s_ready || m_valid))
                $fatal(1, "ASSERT_REGISTERED_CAPTURE");
            if (!H1 && rst_n && pre_k && !error && k_ready)
                $fatal(1, "ASSERT_KEY_CAPTURE");
            #5 clk = 0;
        end
    endtask

    task idle(input integer count);
        integer j;
        begin for (j=0;j<count;j=j+1) tick(); end
    endtask

    task reset_device;
        begin
            #1;
            rst_n = 0;
            s_valid = 0; k_valid = 0; cmd_valid = 0;
            m_ready = 0; ctx_ready = 0;
            old_m_stall = 0; old_c_stall = 0;
            #1; check_reset();
            idle(3);
            rst_n = 1;
            #1;
            first_accept = -1;
            reset_count = reset_count + 1;
        end
    endtask

    task send_beat(input integer data_word, input integer keep_mask,
                   input integer flags);
        integer wait_cycles;
        begin
            if (flags & 2) begin
                k_valid=1; k_data=data_word; k_keep=keep_mask; k_last=flags & 1;
            end else begin
                s_valid=1; s_data=data_word; s_keep=keep_mask; s_last=flags & 1;
            end
            #1;
            wait_cycles=0;
            while (!((flags & 2) ? k_ready : s_ready)) begin
                tick(); #1;
                wait_cycles=wait_cycles+1;
                if (wait_cycles > 20000 || error) $fatal(1, "ASSERT_INPUT_PROGRESS");
            end
            tick();
            k_valid=0; s_valid=0;
        end
    endtask

    task command(input integer code, input [1535:0] image);
        integer wait_cycles;
        begin
            cmd_valid=1; cmd_op=code; cmd_context=image;
            #1; wait_cycles=0;
            while (!cmd_ready) begin
                tick(); #1;
                wait_cycles=wait_cycles+1;
                if (wait_cycles>20000 || error) $fatal(1, "ASSERT_COMMAND_PROGRESS op=%0d",code);
            end
            tick(); cmd_valid=0; #1;
            if (code == 3 && !ctx_valid) $fatal(1, "ASSERT_SAVE_REGISTERED");
            if (code == 5) begin
                if (m_valid || ctx_valid || error || !s_ready || k_ready ||
                    m_digest !== 256'd0 || ctx_data !== 1536'd0)
                    $fatal(1, "ASSERT_CANCEL");
                cancel_count=cancel_count+1; first_accept=-1;
            end
        end
    endtask

    task expect_digest(input integer mode, input integer stall,
                       input integer identity, input [255:0] expected_digest,
                       input integer expected_latency);
        integer wait_cycles, latency, elapsed, j;
        begin
            wait_cycles=0;
            while (!m_valid) begin
                if (error) $fatal(1, "ASSERT_UNEXPECTED_FAULT id=%0d", identity);
                tick(); wait_cycles=wait_cycles+1;
                if (wait_cycles>20000) $fatal(1, "ASSERT_DIGEST_PROGRESS id=%0d",identity);
            end
            latency=cycles-last_accept;
            elapsed=cycles-first_accept+1;
            if(expected_latency>0 && latency != expected_latency)
                $fatal(1,"ASSERT_LATENCY id=%0d expected=%0d actual=%0d",
                       identity,expected_latency,latency);
            if (m_digest !== expected_digest)
                $fatal(1, "ASSERT_DIGEST id=%0d expected=%h actual=%h cycle=%0d",
                       identity,expected_digest,m_digest,cycles);
            for(j=0;j<stall;j=j+1) begin
                if (!m_valid || m_digest !== expected_digest)
                    $fatal(1, "ASSERT_DIGEST_STALL id=%0d",identity);
                tick();
            end
            m_ready=1; tick(); m_ready=0;
            if (m_valid) $fatal(1, "ASSERT_DIGEST_RETIRE");
            comparisons=comparisons+1;
            if (mode) hmac_count=hmac_count+1; else sha_count=sha_count+1;
            $display("COMPARE %0d %0d %0d %0d %0d", mode,identity,latency,elapsed,cycles);
            first_accept=-1;
        end
    endtask

    task save_context(input integer slot, input integer stall, input [1535:0] expected_image);
        integer j;
        begin
            command(3,0);
            if (ctx_data !== expected_image)
                $fatal(1, "ASSERT_CONTEXT slot=%0d expected=%h actual=%h",slot,expected_image,ctx_data);
            slots[slot]=ctx_data; slot_valid[slot]=1;
            for(j=0;j<stall;j=j+1) begin
                if (!ctx_valid || ctx_data !== expected_image) $fatal(1,"ASSERT_CONTEXT_STALL");
                tick();
            end
            ctx_ready=1; tick(); ctx_ready=0;
            if(ctx_valid) $fatal(1,"ASSERT_CONTEXT_RETIRE");
            snapshots=snapshots+1;
            $display("SNAPSHOT %0d %0d",slot,cycles);
        end
    endtask

    task held_snapshot(input integer mode, input integer identity,
                       input [255:0] expected_digest, input [1535:0] expected_image,
                       input integer restore_request);
        begin
            cmd_op=restore_request ? 4 : 3;
            cmd_context=expected_image;
            cmd_valid=1; #1;
            if(cmd_ready) $fatal(1,"ASSERT_INFLIGHT_CONTEXT_READY");
            expect_digest(mode,101,identity,expected_digest,0);
            #1;
            if(!cmd_ready) $fatal(1,"ASSERT_POST_RETIRE_COMMAND_READY");
            tick(); cmd_valid=0; #1;
            if(restore_request) begin
                if(ctx_valid || error) $fatal(1,"ASSERT_HELD_RESTORE");
            end else begin
                if(!ctx_valid || ctx_data !== expected_image) $fatal(1,"ASSERT_HELD_SAVE");
                ctx_ready=1; tick(); ctx_ready=0;
                snapshots=snapshots+1;
                $display("SNAPSHOT 15 %0d",cycles);
            end
            $display("HELD_CONTEXT %0d %0d",restore_request,cycles);
        end
    endtask

    task expect_fault;
        integer j;
        begin
            #1;
            if (!error) $fatal(1,"ASSERT_FAULT_MISSING");
            for(j=0;j<8;j=j+1) begin
                cmd_op=3; #1;
                if (!error || s_ready || k_ready || m_valid || ctx_valid || cmd_ready)
                    $fatal(1,"ASSERT_FAULT_STICKY");
                tick();
            end
            if (!H1) begin
                cmd_op=5; #1;
                if (!cmd_ready) $fatal(1,"ASSERT_FAULT_CANCEL_READY");
            end
            $display("FAULT %0d",cycles);
        end
    endtask

    // A rejected offer may change payload: no transfer has occurred.
    task busy_offer(input integer code, input integer duration);
        integer j;
        begin
            cmd_valid=1; cmd_op=code;
            s_valid=1; k_valid=1; s_keep=15; k_keep=15;
            s_last=1; k_last=1;
            for(j=0;j<duration;j=j+1) begin
                #1;
                if(cmd_ready) $fatal(1,"ASSERT_BUSY_COMMAND op=%0d",code);
                if(s_ready || k_ready) $fatal(1,"ASSERT_BUSY_STREAM");
                cmd_context=j; s_data=j; k_data=~j;
                tick();
            end
            cmd_valid=0; s_valid=0; k_valid=0;
            $display("BUSY %0d %0d %0d",code,duration,cycles);
        end
    endtask

    task race_command(input integer code, input [1535:0] image);
        begin
            cmd_valid=1; cmd_op=code; cmd_context=image;
            s_valid=1; s_data=32'hbadc0ffe; s_keep=15; s_last=1;
            k_valid=1; k_data=32'hbadc0ffe; k_keep=15; k_last=1;
            #1;
            if(!cmd_ready || s_ready || k_ready) $fatal(1,"ASSERT_COMMAND_PRIORITY");
            tick(); cmd_valid=0; s_valid=0; k_valid=0;
            $display("RACE %0d %0d",code,cycles);
        end
    endtask

    initial begin
        rst_n=0;
        #1; check_reset();
        idle(3); rst_n=1; #1;
        if (!$value$plusargs("stim=%s",stimulus)) $fatal(1,"MISSING_STIMULUS");
        fd=$fopen(stimulus,"r");
        if (!fd) $fatal(1,"OPEN_STIMULUS");
        while (!$feof(fd)) begin
            n=$fscanf(fd,"%d %h %h %h %h\n",op,a,b,c,d);
            if (n != 5) begin
                if (!$feof(fd) || n>0) $fatal(1,"MALFORMED_STIMULUS tokens=%0d",n);
            end else begin
                case(op)
                    1: send_beat(a,b,c);
                    2: expect_digest(a & 1,b,c,d[255:0],a >> 1);
                    3: command(a,d);
                    4: save_context(a,b,d);
                    5: begin
                        if(!slot_valid[a]) $fatal(1,"UNINITIALIZED_CONTEXT");
                        command(4,slots[a]); restores=restores+1;
                        $display("RESTORE %0d %0d",a,cycles);
                    end
                    6: idle(a);
                    7: reset_device();
                    8: command(5,0);
                    9: expect_fault();
                    10: begin
                        #1;
                        if (s_ready !== a[0] || k_ready !== b[0] || cmd_ready !== c[0])
                            $fatal(1,"ASSERT_READINESS");
                    end
                    11: busy_offer(a,b);
                    12: race_command(a,d);
                    13: begin
                        guard=0;
                        while(!m_valid) begin
                            tick(); guard=guard+1;
                            if(guard>20000 || error) $fatal(1,"ASSERT_WAIT_DIGEST");
                        end
                        idle(a);
                    end
                    14: begin
                        command(3,0); idle(a);
                    end
                    15: begin
                        // Exercise changing unaccepted data with VALID low.
                        for(i=0;i<a;i=i+1) begin
                            s_data=i*1234567; s_keep=i; s_last=i & 1;
                            k_data=~s_data; tick();
                        end
                    end
                    16: begin
                        if(m_valid || ctx_valid || error) $fatal(1,"ASSERT_STALE_OUTPUT");
                        for(i=0;i<a;i=i+1) begin
                            tick();
                            if(m_valid || ctx_valid || error) $fatal(1,"ASSERT_STALE_OUTPUT");
                        end
                    end
                    17: begin
                        for(i=0;i<a;i=i+1) send_beat(32'h61616161,15, i==a-1);
                    end
                    18: begin
                        // The image and digest occupy separate stimulus rows.
                        n=$fscanf(fd,"%h\n",slots[15]);
                        if(n != 1) $fatal(1,"MALFORMED_HELD_CONTEXT");
                        held_snapshot(a,c,d[255:0],slots[15],b);
                    end
                    19: begin
                        // Exact public stream-stage timing before any block fills.
                        send_beat(a,b,0);
                        for(i=0;i<c-1;i=i+1) begin
                            #1;
                            if(s_ready) $fatal(1,"ASSERT_STAGE_EARLY_READY");
                            tick();
                        end
                        #1;
                        if(s_ready) $fatal(1,"ASSERT_STAGE_EARLY_READY");
                        tick(); #1;
                        if(!s_ready || m_valid) $fatal(1,"ASSERT_STAGE_DRAIN_LATENCY");
                        $display("STAGE %0d %0d",c,cycles);
                    end
                    20: begin
                        if(!m_valid || m_digest[255:128] !== d[127:0])
                            $fatal(1,"ASSERT_RFC4231_TRUNCATED_PREFIX");
                        $display("RFC_PREFIX %h",m_digest[255:128]);
                    end
                    21: begin
                        cmd_valid=1; cmd_op=b[2:0]; s_valid=1;
                        for(i=0;i<a;i=i+1) begin
                            s_data=i; s_keep=i; s_last=i & 1; #1;
                            if(s_ready || !k_ready || cmd_ready || error)
                                $fatal(1,"ASSERT_KEY_EXCLUSIVE");
                            tick();
                        end
                        cmd_valid=0; s_valid=0;
                        $display("KEY_EXCLUSIVE %0d",a);
                    end
                    22: begin
                        ctx_ready=1;
                        command(3,0);
                        if(!ctx_valid || ctx_data !== d)
                            $fatal(1,"ASSERT_SAVE_READY_HIGH_CREATION");
                        tick(); ctx_ready=0;
                        if(ctx_valid) $fatal(1,"ASSERT_SAVE_READY_HIGH_RETIRE");
                        snapshots=snapshots+1;
                        $display("SNAPSHOT 15 %0d",cycles);
                    end
                    23: m_ready=1;
                    25: begin m_ready=1; ctx_ready=1; end
                    default: $fatal(1,"UNKNOWN_STIMULUS");
                endcase
            end
        end
        $fclose(fd);
        $display("RESULT %0d %0d %0d %0d %0d %0d %0d %0d",
                 comparisons,sha_count,hmac_count,snapshots,restores,cycles,reset_count,cancel_count);
        $finish;
    end
endmodule
