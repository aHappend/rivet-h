"""Generate bounded, self-checking Icarus benches; no test logic in RTL."""

TOP = r"""
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg rst_n, s_valid=0, s_last=0, m_ready=0;
reg [31:0] s_data=0;
reg [3:0] s_keep=0;
wire s_ready,m_valid,error;
wire [255:0] m_digest;
rivet_h1_top dut(.*);
integer cycle=0, ni=0, no=0, blocks=0, rounds=0, completions=0;
integer got_in=0, got_out=0, active_launch=-1, round_seen=0;
integer permit_retire=0;
integer trace_on=0, msg_id=-1, block_id=0;
integer prev_stall=0;
reg [255:0] prev_digest;
reg input_stall=0;
reg [36:0] held_input;
integer reset_checks=0, async_checks=0;

task reset_outputs;
begin
 if (s_ready !== 0 || m_valid !== 0 || m_digest !== 256'd0 || error !== 0)
   $fatal(1,"RESET_OUTPUT_X_OR_VALUE cycle=%0d",cycle);
 reset_checks=reset_checks+1;
end
endtask

always @(negedge clk) if (!rst_n) reset_outputs;
always @(posedge clk) begin
 cycle=cycle+1;
 if (!rst_n) begin
   reset_outputs;
   prev_stall=0; input_stall=0; active_launch=-1;
 end else begin
   if ((^{s_ready,m_valid,error}) === 1'bx) $fatal(1,"UNKNOWN_CONTROL");
   if (m_valid && (^m_digest === 1'bx)) $fatal(1,"UNKNOWN_DIGEST");
   if (prev_stall && (m_valid !== 1 || m_digest !== prev_digest))
     $fatal(1,"OUTPUT_STABILITY");
   if (input_stall && {s_valid,s_data,s_keep,s_last} !== {1'b1,held_input})
     $fatal(1,"PRODUCER_STABILITY");
   if (m_valid && s_ready) $fatal(1,"INPUT_WITH_PENDING_DIGEST");
   prev_stall=m_valid && !m_ready; prev_digest=m_digest;
   input_stall=s_valid && !s_ready; held_input={s_data,s_keep,s_last};
   if (dut.u_compress.start) begin
     if (active_launch>=0) $fatal(1,"OVERLAPPED_BLOCK");
     active_launch=cycle; round_seen=0; blocks=blocks+1;
     if (trace_on) $display("B %0d %0d %0d %0128h %064h",
       msg_id,block_id,cycle,dut.u_compress.block_data,dut.u_compress.state_in);
   end
   if (dut.u_compress.state==1) begin
     if (cycle != active_launch+round_seen+1 ||
         dut.u_compress.round_index !== round_seen[5:0])
       $fatal(1,"ROUND_CYCLE");
     if (trace_on) $display("W %0d %0d %0d %08h",
       msg_id,block_id,round_seen,dut.u_compress.schedule_word);
     round_seen=round_seen+1; rounds=rounds+1;
   end
 end
 #1;
 if (rst_n && dut.u_compress.done) begin
   if (active_launch<0 || cycle!=active_launch+65 || round_seen!=64)
     $fatal(1,"COMPLETION_CYCLE");
   if (trace_on) $display("C %0d %0d %0d %064h",
       msg_id,block_id,cycle,dut.u_compress.state_out);
   completions=completions+1; active_launch=-1; block_id=block_id+1;
 end
end

task automatic step(input integer v,input [31:0] data,input [3:0] keep,
                    input integer last,input integer ready);
begin
 @(negedge clk);
 s_valid=v; s_data=data; s_keep=keep; s_last=last; m_ready=ready;
 @(posedge clk);
 got_in=rst_n && s_valid && s_ready;
 got_out=rst_n && m_valid && m_ready;
 if(got_out && !permit_retire) $fatal(1,"UNEXPECTED_OUTPUT_HANDSHAKE");
 if (got_in) ni=ni+1;
 if (got_out) no=no+1;
 #2;
end
endtask

task automatic idle(input integer count,input integer ready);
integer t;
begin for(t=0;t<count;t=t+1) step(0,0,0,0,ready); end
endtask

task automatic reset_core;
begin
 @(negedge clk); #1;
 rst_n=0; s_valid=0; m_ready=0;
 #1; reset_outputs; async_checks=async_checks+1;
 @(posedge clk); #2;
 @(negedge clk); rst_n=1;
 #1;
 if(s_ready !== 1 || m_valid !== 0 || error !== 0) $fatal(1,"RESET_RECOVERY");
end
endtask

task automatic beat(input [31:0] data,input [3:0] keep,input integer last,
                    input integer ready);
integer wait_cycles;
begin
 wait_cycles=0;
 begin : wait_accept
   while(1) begin
     step(1,data,keep,last,ready);
     if(got_in) disable wait_accept;
     wait_cycles=wait_cycles+1;
     if(wait_cycles>512) $fatal(1,"INPUT_PROGRESS");
   end
 end
end
endtask

task automatic recover_abc;
integer e,t,n_before;
begin
 msg_id=-1; trace_on=0; n_before=no;
 beat(32'h616263a7,4'b1110,1,0); e=cycle;
 for(t=1;t<=68;t=t+1) begin
   step(0,0,0,0,0);
   if(m_valid !== (t==68)) $fatal(1,"RECOVERY_LATENCY");
 end
 if(m_digest !== 256'hba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad)
   $fatal(1,"RECOVERY_DIGEST");
 permit_retire=1; step(0,0,0,0,1); permit_retire=0;
 if(!got_out || no!=n_before+1 || s_ready!==1) $fatal(1,"RECOVERY_RETIRE");
end
endtask

task automatic fault_hold;
integer t,n_before;
begin
 n_before=no;
 if(error !== 1 || m_valid !== 0 || s_ready !== 0) $fatal(1,"FAULT_ENTRY");
 for(t=0;t<140;t=t+1) begin
   step(1,32'hdeadbeef,15,1,1);
   if(error !== 1 || m_valid !== 0 || s_ready !== 0 || got_in || got_out)
     $fatal(1,"FAULT_STICKY");
 end
 if(no!=n_before) $fatal(1,"ABORTED_OUTPUT");
 reset_core;
 recover_abc;
end
endtask

task automatic reset_priority(input integer kind);
integer before_outputs;
begin
 reset_core;
 if(kind==2) begin
   beat(32'h616263ff,14,1,0);
   idle(68,0);
   if(m_valid!==1) $fatal(1,"RESET_OUTPUT_PRECONDITION");
 end else if(s_ready!==1) $fatal(1,"RESET_INPUT_PRECONDITION");
 before_outputs=no;
 @(negedge clk);
 s_valid=1; s_data=32'h12345678; s_keep=(kind==1?5:15);
 s_last=1; m_ready=1;
 #1; rst_n=0;
 #1; reset_outputs; async_checks=async_checks+1;
 @(posedge clk);
 if(s_ready!==0 || m_valid!==0 || error!==0) $fatal(1,"RESET_HANDSHAKE_PRIORITY");
 #2;
 @(negedge clk); s_valid=0; m_ready=0; rst_n=1;
 idle(140,1);
 if(no!=before_outputs || error!==0 || m_valid!==0) $fatal(1,"RESET_PRIORITY_STALE");
 recover_abc;
end
endtask

task automatic protocol;
integer mask,last,t,offset,k,n_before,cancel_count,faults,continuous_stalls;
reg [63:0] seed_count;
begin
 trace_on=0; msg_id=-1; faults=0; cancel_count=0;
 // Invalid masks on accepted beats, then independent reset recovery.
 for(last=0;last<=1;last=last+1)
   for(mask=0;mask<16;mask=mask+1)
     if((!last && mask!=15) ||
        (last && mask!=0 && mask!=8 && mask!=12 && mask!=14 && mask!=15)) begin
       reset_core;
       beat(32'h76543210,mask[3:0],last,0);
       fault_hold; faults=faults+1;
     end
 reset_core;
 beat(32'h01234567,15,0,0);
 beat(0,0,1,0); fault_hold; faults=faults+1;
 // Invalid inactive input is ignored; payload/gaps must not alter message.
 reset_core;
 for(t=0;t<20;t=t+1) step(0,32'hffffffff,5,1,t%2);
 if(error!==0 || s_ready!==1) $fatal(1,"INACTIVE_ERROR");
 recover_abc;
 // Top-level overflow: state seeding is only arithmetic coverage, not hashing.
 for(k=1;k<=4;k=k+1) begin
   reset_core;
   @(negedge clk); dut.u_length.byte_count=64'h1fffffffffffffff;
   beat(32'haabbccdd,(k==1?8:k==2?12:k==3?14:15),1,0);
   fault_hold; faults=faults+1;
 end
 // Cancel gather, preparation, launch, early/middle/final rounds,
 // pending completion and a reserved output, between active clock edges.
 for(k=0;k<10;k=k+1) begin
   reset_core; n_before=no;
   if(k==0) beat(32'h12345678,15,0,0);
   else begin
     beat(32'h616263ff,14,1,0);
     case(k)
       1: offset=0;
       2: offset=1;
       3: offset=2;
       4: offset=3;
       5: offset=34;
       6: offset=66;
       7: offset=67;
       8: offset=68;
       9: offset=80;
     endcase
     idle(offset,0);
     if(k>=8 && m_valid!==1) $fatal(1,"CANCEL_RESERVATION_NOT_PRESENT");
   end
   reset_core;
   idle(140,1);
   if(no!=n_before || m_valid!==0) $fatal(1,"STALE_AFTER_RESET");
   recover_abc; cancel_count=cancel_count+1;
 end
 // Continuous valid for the next legal message throughout compression and
 // output retirement. The same beat is held until its eventual acceptance.
 reset_core;
 beat(32'h616263ee,14,1,0);
 n_before=no; continuous_stalls=0;
 for(t=1;t<=326;t=t+1) begin
   step(1,32'h616263ab,14,1,0);
   if(got_in || got_out) $fatal(1,"EARLY_NEXT_MESSAGE");
   if(t>=68 && m_valid!==1) $fatal(1,"MISSING_STALLED_DIGEST");
   if(t>68 && m_valid===1) continuous_stalls=continuous_stalls+1;
 end
 permit_retire=1; step(1,32'h616263ab,14,1,1); permit_retire=0;
 if(got_in || !got_out || no!=n_before+1) $fatal(1,"RETIRE_COINCIDENCE");
 step(1,32'h616263ab,14,1,0);
 if(!got_in) $fatal(1,"NEXT_MESSAGE_NOT_ACCEPTED");
 for(t=1;t<=68;t=t+1) step(0,0,0,0,0);
 if(m_valid!==1 ||
    m_digest!==256'hba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad)
   $fatal(1,"NEXT_MESSAGE_INITIAL_CHAIN");
 permit_retire=1; step(0,0,0,0,1); permit_retire=0;
 for(k=0;k<3;k=k+1) reset_priority(k);
 if(continuous_stalls<256) $fatal(1,"CONTINUOUS_STALL_COVERAGE");
 $display("P %0d %0d %0d 1 3",faults,cancel_count,continuous_stalls);
end
endtask

integer fd,rc,id,length,nbeats,mode,stall,trace_flag,gap,last_i,keep_i;
integer i,t,first_edge,final_edge,valid_edge,retire_edge,base_blocks,base_rounds;
integer message_blocks,first_global=-1,last_global=-1,transactions=0;
integer stall_actual,expected_latency,waited;
reg [31:0] data_i;
reg [255:0] expected;
reg [1023:0] stimulus_path;
integer do_protocol;
initial begin
 rst_n=0;
 // Reset starts asserted at time zero, including Active-region t=5 checks.
 #0; reset_outputs;
 #1; reset_outputs;
 @(posedge clk); #2;
 @(negedge clk); rst_n=1;
 if(!$value$plusargs("stimulus=%s",stimulus_path)) $fatal(1,"NO_STIMULUS");
 if(!$value$plusargs("protocol=%d",do_protocol)) do_protocol=0;
 fd=$fopen(stimulus_path,"r");
 if(!fd) $fatal(1,"STIMULUS_OPEN");
 begin : messages
 while(1) begin
   rc=$fscanf(fd,"%d %d %d %d %d %d %h\n",
              id,length,nbeats,mode,stall,trace_flag,expected);
   if(rc==-1) disable messages;
   if(rc!=7) $fatal(1,"MALFORMED_HEADER %0d",rc);
   msg_id=id; block_id=0; trace_on=trace_flag;
   base_blocks=blocks; base_rounds=rounds;
   first_edge=-1; final_edge=-1;
   for(i=0;i<nbeats;i=i+1) begin
     rc=$fscanf(fd,"%h %d %d %d\n",data_i,keep_i,last_i,gap);
     if(rc!=4) $fatal(1,"MALFORMED_BEAT");
     for(t=0;t<gap;t=t+1) step(0,32'hffffffff,5,1,mode==0);
     beat(data_i,keep_i[3:0],last_i,mode==0);
     if(first_edge<0) first_edge=cycle;
     if(first_global<0) first_global=cycle;
     if(last_i) final_edge=cycle;
     if(!last_i && (i%16)==15) begin
       for(t=1;t<=68;t=t+1) begin
         step(0,0,5,1,mode==0);
         if(s_ready !== (t==68) || m_valid!==0 || error!==0)
           $fatal(1,"NONFINAL_CYCLE");
       end
     end
   end
   if(final_edge<0 || error!==0 || s_ready!==0) $fatal(1,"FINAL_ACCEPT");
   expected_latency=((length%64)>=56 || (length>0 && length%64==0))?135:68;
   for(t=1;t<=expected_latency;t=t+1) begin
     // Ready changes directly around the first-valid edge for mode 2.
     step(0,32'h89abcdef,5,1,mode==0 || (mode==2 && t<expected_latency));
     if(m_valid !== (t==expected_latency) || error!==0 || s_ready!==0)
       $fatal(1,"FINAL_LATENCY id=%0d t=%0d",id,t);
   end
   valid_edge=cycle; stall_actual=0;
   // Digest comparison is performed independently by Python on this record.
   $display("D %0d %064h",id,m_digest);
   for(t=0;t<stall;t=t+1) begin
     step(0,32'hfedcba98,5,1,0);
     if(m_valid!==1 || s_ready!==0 || error!==0) $fatal(1,"STALL_STATE");
     stall_actual=stall_actual+1;
   end
   permit_retire=1; step(0,0,5,1,1); permit_retire=0;
   if(!got_out || m_valid!==0 || s_ready!==1) $fatal(1,"RETIRE");
   retire_edge=cycle; last_global=cycle;
   message_blocks=blocks-base_blocks;
   if(message_blocks!=(length+72)/64 || rounds-base_rounds!=64*message_blocks)
     $fatal(1,"BLOCK_ROUND_COUNTS");
   $display("T %0d %0d %0d %0d %0d %0d %0d %0d %0d",
     id,first_edge,final_edge,valid_edge,retire_edge,stall_actual,
     message_blocks,rounds-base_rounds,length);
   transactions=transactions+1;
 end
 end
 $fclose(fd);
 if(do_protocol) protocol;
 idle(140,1);
 if(m_valid!==0 || error!==0) $fatal(1,"TRAILING_OUTPUT");
 $display("END %0d %0d %0d %0d %0d %0d %0d %0d",
   transactions,blocks,rounds,completions,cycle,reset_checks,async_checks,no);
 $finish;
end
initial begin
 // Simulated progress bound, not a wall-clock deadline.
 #2000000000; $fatal(1,"SIMULATED_PROGRESS_BOUND");
end
endmodule
"""

LENGTH = r"""
`timescale 1ns/1ps
module tb;
reg clk=0;
always #5 clk=~clk;
reg rst_n,clear=0,accept=0;
reg [2:0] beat_bytes=0;
wire [63:0] byte_count,next_byte_count;
wire overflow;
rivet_h1_length dut(.*);
integer checks=0,k,j;
reg [63:0] bases[0:8];
reg [64:0] expected;
task automatic trial(input [63:0] base,input integer n,input integer a,input integer c);
begin
 @(negedge clk); dut.byte_count=base; beat_bytes=n; accept=a; clear=c;
 expected={1'b0,base}+n;
 #1;
 if(next_byte_count !== expected[63:0] ||
    overflow !== (expected>65'h01fffffffffffffff)) $fatal(1,"LENGTH_PROPOSAL");
 @(posedge clk); #1;
 if(byte_count !== (c ? 64'd0 :
      (a && expected<=65'h01fffffffffffffff ? expected[63:0] : base)))
   $fatal(1,"LENGTH_COMMIT");
 $display("A %016h %0d %0d %0d %017h %016h",base,n,a,c,expected,byte_count);
 checks=checks+1;
end
endtask
initial begin
 rst_n=0;
 #1; if(byte_count!==0) $fatal(1,"LENGTH_RESET");
 @(posedge clk); #1;
 @(negedge clk); rst_n=1;
 bases[0]=0; bases[1]=64'h1ffffffc; bases[2]=64'h20000000;
 bases[3]=64'hfffffffc; bases[4]=64'h100000000;
 bases[5]=64'h1ffffffffffffffb; bases[6]=64'h1ffffffffffffffe;
 bases[7]=64'h1fffffffffffffff; bases[8]=64'hfffffffffffffffe;
 for(k=0;k<9;k=k+1) for(j=0;j<=4;j=j+1) begin
   trial(bases[k],j,1,0);
   trial(bases[k],j,0,0);
   trial(bases[k],j,1,1);
 end
 $display("LEND %0d",checks); $finish;
end
initial begin #100000; $fatal(1,"LENGTH_PROGRESS"); end
endmodule
"""
