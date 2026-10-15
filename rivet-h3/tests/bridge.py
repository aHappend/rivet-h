"""Generated public-pin Icarus transactor; no DUT hierarchical observations."""


def testbench(partial=0, standalone=False):
    if standalone:
        instance = """
wire [255:0] h2_digest;
wire [1535:0] h2_context;
wire h2_error;
assign m_digest = {256'd0,h2_digest};
assign ctx_data = {768'd0,h2_context};
assign error = {3'd0,h2_error};
assign m_channel = 0;
assign ctx_channel = 0;
assign m_alg = 0;
rivet_h2_top #(.PARTIAL_BEATS(PARTIAL)) dut(
 .clk(clk),.rst_n(rst_n),.s_valid(s_valid),.s_ready(s_ready),
 .s_data(s_data),.s_keep(s_keep),.s_last(s_last),
 .k_valid(k_valid),.k_ready(k_ready),.k_data(k_data),.k_keep(k_keep),.k_last(k_last),
 .cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_op(cmd_op),
 .cmd_context(cmd_context[1535:0]),.m_valid(m_valid),.m_ready(m_ready),
 .m_digest(h2_digest),.ctx_valid(ctx_valid),.ctx_ready(ctx_ready),
 .ctx_data(h2_context),.error(h2_error));
"""
    else:
        instance = """
rivet_h3_top #(.PARTIAL_BEATS(PARTIAL)) dut(
 .clk(clk),.rst_n(rst_n),.s_valid(s_valid),.s_ready(s_ready),.s_channel(s_channel),
 .s_data(s_data),.s_keep(s_keep),.s_last(s_last),
 .k_valid(k_valid),.k_ready(k_ready),.k_channel(k_channel),
 .k_data(k_data),.k_keep(k_keep),.k_last(k_last),
 .cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_channel(cmd_channel),
 .cmd_op(cmd_op),.cmd_context(cmd_context),.m_valid(m_valid),.m_ready(m_ready),
 .m_channel(m_channel),.m_alg(m_alg),.m_digest(m_digest),
 .ctx_valid(ctx_valid),.ctx_ready(ctx_ready),.ctx_channel(ctx_channel),
 .ctx_data(ctx_data),.error(error));
"""
    return r"""
`timescale 1ns/1ps
module tb;
localparam PARTIAL = @PARTIAL@;
localparam STANDALONE = @STANDALONE@;
reg clk=0;
reg rst_n;
always #5 clk=~clk;
reg s_valid=0,k_valid=0,cmd_valid=0;
wire s_ready,k_ready,cmd_ready;
reg [1:0] s_channel=0,k_channel=0,cmd_channel=0;
reg [31:0] s_data=0,k_data=0;
reg [3:0] s_keep=0,k_keep=0;
reg s_last=0,k_last=0;
reg [2:0] cmd_op=0;
reg [2303:0] cmd_context=0;
wire m_valid,ctx_valid;
reg m_ready=1,ctx_ready=1;
wire [1:0] m_channel,m_alg,ctx_channel;
wire [511:0] m_digest;
wire [2303:0] ctx_data;
wire [3:0] error;
reg [511:0] expected_digest[0:3];
reg [1:0] expected_alg[0:3];
reg pending[0:3],cpending[0:3];
reg [2303:0] expected_context[0:3],snapshot[0:31];
integer context_slot[0:3],ident[0:3],payload_bytes[0:3];
integer first_beat[0:3],last_beat[0:3],first_valid[0:3];
integer cycle=0,compared=0,contexts=0,beats=0,keybeats=0;
integer stall_cycles=0,context_stall_cycles=0,coincident=0;
integer random_stall_cycles=0;
integer reset_edges=0,source_bubbles=0;
integer retirement_order[0:65535],order_count=0;
integer retirement_cycle[0:65535];
integer context_order[0:65535],context_cycle[0:65535],context_count=0;
reg [515:0] held_digest;
reg [2305:0] held_context;
reg was_stalled=0,was_cstalled=0;
reg hs_s,hs_k,hs_cmd,sampled_s_ready;
reg random_ready=0;
reg [31:0] rng=17;
integer i;
@INSTANCE@
task check_reset;
begin
 if ({s_ready,k_ready,cmd_ready,m_valid,m_channel,m_alg,m_digest,
      ctx_valid,ctx_channel,ctx_data,error} !== 2831'd0)
   $fatal(1,"ASSERT RESET_ZERO t=%0t",$time);
end
endtask
always @(negedge clk) begin
 if (!rst_n) check_reset();
 else begin
   if ((^{s_ready,k_ready,cmd_ready,m_valid,ctx_valid,error}) === 1'bx)
     $fatal(1,"ASSERT NEGEDGE_ACTIVE_XZ control");
   if (m_valid && (^{m_channel,m_alg,m_digest}) === 1'bx)
     $fatal(1,"ASSERT NEGEDGE_ACTIVE_XZ digest");
   if (ctx_valid && (^{ctx_channel,ctx_data}) === 1'bx)
     $fatal(1,"ASSERT NEGEDGE_ACTIVE_XZ context");
 end
end
always @(posedge clk) begin
 cycle=cycle+1;
 hs_s=s_valid && s_ready;
 hs_k=k_valid && k_ready;
 hs_cmd=cmd_valid && cmd_ready;
 sampled_s_ready=s_ready;
 if (!rst_n) begin
   check_reset();
   reset_edges=reset_edges+1;
   was_stalled=0; was_cstalled=0;
 end else begin
   if ((^{s_ready,k_ready,cmd_ready,m_valid,ctx_valid,error}) === 1'bx)
     $fatal(1,"ASSERT ACTIVE_XZ control cycle=%0d",cycle);
   if (was_stalled && ({m_valid,m_channel,m_alg,m_digest} !== {1'b1,held_digest}))
     $fatal(1,"ASSERT DIGEST_STABILITY cycle=%0d",cycle);
   if (was_cstalled && ({ctx_valid,ctx_channel,ctx_data} !== {1'b1,held_context}))
     $fatal(1,"ASSERT CONTEXT_STABILITY cycle=%0d",cycle);
   was_stalled=m_valid && !m_ready;
   was_cstalled=ctx_valid && !ctx_ready;
   held_digest={m_channel,m_alg,m_digest};
   held_context={ctx_channel,ctx_data};
   if (was_stalled) stall_cycles=stall_cycles+1;
   if (was_stalled && random_ready) random_stall_cycles=random_stall_cycles+1;
   if (was_cstalled) context_stall_cycles=context_stall_cycles+1;
   if (hs_s) begin
     beats=beats+1;
     if (pending[s_channel]) begin
       if (first_beat[s_channel]<0) first_beat[s_channel]=cycle;
       last_beat[s_channel]=cycle;
     end
   end
   if (hs_k) keybeats=keybeats+1;
   if (!s_valid) source_bubbles=source_bubbles+1;
   if (m_valid) begin
     if ((^{m_channel,m_alg,m_digest}) === 1'bx)
       $fatal(1,"ASSERT ACTIVE_XZ digest");
     if (!pending[m_channel]) $fatal(1,"ASSERT EXTRA_DIGEST ch=%0d",m_channel);
     if ((!STANDALONE && m_alg !== expected_alg[m_channel]) ||
         m_digest !== expected_digest[m_channel])
       $fatal(1,"ASSERT DIGEST_ORACLE ch=%0d id=%0d got=%h expected=%h alg=%0d",
              m_channel,ident[m_channel],m_digest,expected_digest[m_channel],m_alg);
     if (first_valid[m_channel]<0) first_valid[m_channel]=cycle;
     if (m_ready) begin
       $display("DIGEST %0d %0d %0d %0d %0d %0d %0d %0d",
          ident[m_channel],m_channel,expected_alg[m_channel],payload_bytes[m_channel],
          first_beat[m_channel],last_beat[m_channel],first_valid[m_channel],cycle);
       compared=compared+1;
       retirement_order[order_count]=m_channel;
       retirement_cycle[order_count]=cycle;
       order_count=order_count+1;
       pending[m_channel]=0;
     end
   end
   if (ctx_valid) begin
     if ((^{ctx_channel,ctx_data}) === 1'bx) $fatal(1,"ASSERT ACTIVE_XZ context");
     if (!cpending[ctx_channel]) $fatal(1,"ASSERT EXTRA_CONTEXT");
     if (ctx_data !== expected_context[ctx_channel])
       $fatal(1,"ASSERT CONTEXT_ORACLE ch=%0d got=%h expected=%h",
              ctx_channel,ctx_data,expected_context[ctx_channel]);
     if (ctx_ready) begin
       snapshot[context_slot[ctx_channel]]=ctx_data;
       cpending[ctx_channel]=0;
       contexts=contexts+1;
       context_order[context_count]=ctx_channel;
       context_cycle[context_count]=cycle;
       context_count=context_count+1;
       $display("CONTEXT %0d %0d %h",ctx_channel,cycle,ctx_data);
     end
   end
   if (ctx_valid && ctx_ready && m_valid && m_ready) coincident=coincident+1;
 end
 if (cycle>100000000) $fatal(1,"ASSERT CYCLE_TIMEOUT");
end
always @(negedge clk) begin
 if (rst_n && random_ready) begin
   rng=rng ^ (rng<<13); rng=rng ^ (rng>>17); rng=rng ^ (rng<<5);
   m_ready=(rng[2:0]!=0);
 end
end
task tick;
begin @(posedge clk); #1; end
endtask
task delay_cycles(input integer n);
integer j;
begin for(j=0;j<n;j=j+1) tick(); end
endtask
task command(input integer ch,input integer op,input [2303:0] data);
integer timeout;
begin
 @(negedge clk); cmd_channel=ch; cmd_op=op; cmd_context=data; cmd_valid=1;
 tick(); timeout=0;
 while(!hs_cmd) begin
   tick(); timeout=timeout+1;
   if(timeout>2000000) $fatal(1,"ASSERT COMMAND_TIMEOUT ch=%0d op=%0d",ch,op);
 end
 @(negedge clk); cmd_valid=0;
end
endtask
task beat(input integer keyport,input integer ch,input [31:0] data,
          input [3:0] keep,input integer last);
integer timeout;
begin
 @(negedge clk);
 if(keyport) begin k_valid=1;k_channel=ch;k_data=data;k_keep=keep;k_last=last; end
 else begin s_valid=1;s_channel=ch;s_data=data;s_keep=keep;s_last=last; end
 tick();timeout=0;
 while(!(keyport ? hs_k : hs_s)) begin
   tick();timeout=timeout+1;
   if(timeout>2000000) $fatal(1,"ASSERT BEAT_TIMEOUT ch=%0d key=%0d",ch,keyport);
 end
 @(negedge clk);
 if(keyport) k_valid=0; else s_valid=0;
end
endtask
task drain;
integer timeout;
begin
 timeout=0;
 while(pending[0] || pending[1] || pending[2] || pending[3] ||
       cpending[0] || cpending[1] || cpending[2] || cpending[3]) begin
   tick(); timeout=timeout+1;
   if(timeout>2000000) $fatal(1,"ASSERT RESPONSE_TIMEOUT");
 end
end
endtask
integer fd,n,op,a,b,c,d,e;
reg [2303:0] value;
reg [4095:0] program_path;
initial begin
 rst_n=0;
 for(i=0;i<4;i=i+1) begin
   pending[i]=0;cpending[i]=0;expected_alg[i]=0;
   first_beat[i]=-1;last_beat[i]=-1;first_valid[i]=-1;
 end
 #1; check_reset();
 delay_cycles(3);
 @(negedge clk);rst_n=1;
 if(!$value$plusargs("PROGRAM=%s",program_path)) $fatal(1,"missing PROGRAM");
 fd=$fopen(program_path,"r");
 if(!fd) $fatal(1,"program open");
 while(!$feof(fd)) begin
   n=$fscanf(fd,"%h %h %h %h %h %h %h\n",op,a,b,c,d,e,value);
   if(n!=7 && !((n==0 || n==-1) && $feof(fd))) $fatal(1,"malformed program %0d",n);
   if(n==7) begin
     case(op)
      0: delay_cycles(a);
      1: command(a,b,value);
      2: beat(0,a,value[31:0],b,c);
      3: beat(1,a,value[31:0],b,c);
      4: begin
        if(pending[a]) $fatal(1,"expectation overwrite");
        pending[a]=1;expected_alg[a]=b;expected_digest[a]=value[511:0];
        ident[a]=c;payload_bytes[a]=d;
        first_beat[a]=-1;last_beat[a]=-1;first_valid[a]=-1;
      end
      5: drain();
      6: begin
        @(negedge clk);#1;rst_n=0;s_valid=0;k_valid=0;cmd_valid=0;
        for(i=0;i<4;i=i+1) begin pending[i]=0;cpending[i]=0;end
        #1;check_reset();
        delay_cycles(3);@(negedge clk);rst_n=1;
      end
      7: begin @(negedge clk);random_ready=c;m_ready=a;ctx_ready=b; end
      8: begin
        if(cpending[a]) $fatal(1,"context expectation overwrite");
        cpending[a]=1;context_slot[a]=b;expected_context[a]=value;
      end
      9: command(a,4,b ? {768'd0,snapshot[c][1535:0]} : snapshot[c]);
      10: begin
        delay_cycles(b);
        if(error !== a[3:0]) $fatal(1,"ASSERT ERROR_MASK got=%h expected=%h",error,a);
        $display("ERROR_CHECK %0d %0d",a,cycle);
      end
      11: begin
        if(order_count<b+1 || retirement_order[b]!=a)
          $fatal(1,"ASSERT ROUND_ROBIN index=%0d expected=%0d",b,a);
        if(c && b>0 && retirement_cycle[b]-retirement_cycle[b-1]!=c)
          $fatal(1,"ASSERT SELECTION_BUBBLE");
      end
      12: begin
        if(stall_cycles<a || context_stall_cycles<b || coincident<c)
          $fatal(1,"ASSERT COVERAGE_STALL digest=%0d context=%0d simultaneous=%0d",
                 stall_cycles,context_stall_cycles,coincident);
      end
      13: begin
        @(negedge clk);cmd_channel=a;cmd_op=b;cmd_context=value;cmd_valid=1;
        tick();
        if(cmd_ready !== 1'b0 || hs_cmd) $fatal(1,"ASSERT COMMAND_BACKPRESSURE");
        @(negedge clk);cmd_valid=0;
      end
      14: begin
        $display("MARK %0d %0d %0d %0d",a,cycle,compared,keybeats);
      end
      15: begin
        @(negedge clk);
        s_channel=a;cmd_channel=a;cmd_op=b;cmd_valid=1;
        s_valid=1;s_keep=15;s_data=32'hdeadbeef;s_last=0;
        k_channel=a;k_valid=1;k_keep=15;k_data=32'h01020304;k_last=0;
        tick();
        if(!hs_cmd || hs_s || hs_k || s_ready !== 1'b0 || k_ready !== 1'b0)
          $fatal(1,"ASSERT COMMAND_PRIORITY");
        @(negedge clk);cmd_valid=0;s_valid=0;k_valid=0;
      end
      16: begin
        @(negedge clk);s_channel=a;k_channel=a;cmd_channel=a;cmd_op=0;
        #1;
        if(s_ready !== b[0] || k_ready !== c[0] || cmd_ready !== d[0])
          $fatal(1,"ASSERT READY_MODE ch=%0d s=%b k=%b cmd=%b",a,s_ready,k_ready,cmd_ready);
        $display("READY_CHECK %0d %0d %0d %0d %0d",a,b,c,d,cycle);
      end
      17: rng=value[31:0];
      18: begin order_count=0;context_count=0;end
      19: begin
        if(m_valid !== a[0] || ctx_valid !== b[0])
          $fatal(1,"ASSERT RESPONSE_PRECONDITION m=%b ctx=%b",m_valid,ctx_valid);
      end
      20: begin
        if(context_count<b+1 || context_order[b]!=a)
          $fatal(1,"ASSERT CONTEXT_ROUND_ROBIN");
        if(c && b>0 && context_cycle[b]-context_cycle[b-1]!=c)
          $fatal(1,"ASSERT CONTEXT_SELECTION_BUBBLE");
      end
      21: begin
        @(negedge clk);
        s_channel=0;s_valid=1;s_data=32'h6f6e6521;s_keep=15;s_last=1;
        k_channel=1;k_valid=1;k_data=32'h6b657921;k_keep=15;k_last=1;
        cmd_channel=2;cmd_valid=1;cmd_op=6;cmd_context=0;
        tick();
        if(!hs_s || !hs_k || !hs_cmd) $fatal(1,"ASSERT INDEPENDENT_TRANSFERS");
        @(negedge clk);s_valid=0;k_valid=0;cmd_valid=0;
        $display("INDEPENDENT_TRANSFERS %0d",cycle);
      end
      22: begin
        beat(0,a,32'h61626364,15,0);
        for(i=1;i<=4;i=i+1) begin
          tick();
          if(sampled_s_ready !== 1'b0 || m_valid !== 1'b0)
            $fatal(1,"ASSERT STAGING_CADENCE edge=%0d",i);
        end
        if(s_ready !== 1'b1) $fatal(1,"ASSERT STAGING_RELEASE");
        $display("STAGING_CADENCE %0d %0d",a,cycle);
      end
      23: begin
        if(random_stall_cycles<a || source_bubbles<b)
          $fatal(1,"ASSERT RANDOM_STALL_COVERAGE stalls=%0d bubbles=%0d",
                 random_stall_cycles,source_bubbles);
      end
      24: begin
        @(negedge clk);#1;rst_n=0;
        s_valid=1;k_valid=1;cmd_valid=1;
        s_channel=3;k_channel=3;cmd_channel=3;cmd_op=7;
        for(i=0;i<4;i=i+1) begin pending[i]=0;cpending[i]=0;end
        #1;check_reset();delay_cycles(3);
        @(negedge clk);s_valid=0;k_valid=0;cmd_valid=0;rst_n=1;
      end
      25: $display("COVER %0d %0d",a,cycle);
      default: $fatal(1,"unknown instruction");
     endcase
   end
 end
 drain();delay_cycles(20);
 if(error !== 4'd0) $fatal(1,"ASSERT FINAL_ERROR %h",error);
 $display("SUMMARY %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
          compared,contexts,beats,keybeats,cycle,stall_cycles,context_stall_cycles,
          coincident,reset_edges,source_bubbles,random_stall_cycles);
 $finish;
end
endmodule
""".replace("@PARTIAL@", str(partial)).replace(
        "@STANDALONE@", str(int(standalone))).replace("@INSTANCE@", instance)
