// Serialize cached recalculations and coalesce rapid edits; never fetch quotes.
class LiveRules {
  constructor({save,busy=()=>false,delay=450,onError=()=>{}}){Object.assign(this,{save,busy,delay,onError});this.next=null;this.running=false;this.timer=null;}
  schedule(value){this.next=value;clearTimeout(this.timer);this.timer=setTimeout(()=>this.resume(),this.delay);}
  async resume(){
    if(this.running||this.busy()||!this.next)return;
    const value=this.next;this.next=null;this.running=true;
    try{await this.save(value);}catch(error){this.onError(error);}
    finally{this.running=false;if(this.next&&!this.busy())this.schedule(this.next);}
  }
}
if(typeof module!=='undefined')module.exports={LiveRules};
