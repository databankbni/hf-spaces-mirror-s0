FROM alpine:latest

# 1. 安装基础依赖
RUN apk update && \
    apk add --no-cache nginx curl && \
    mkdir -p /var/log/nginx /var/run /var/www/localhost/htdocs

# 2. 生成完美适配手机与PC、带丝滑计时器的经典扫雷游戏
RUN cat <<'EOF' > /var/www/localhost/htdocs/index.html
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"><title>经典扫雷</title><style>
body{text-align:center;font-family:monospace;background:#222;color:#fff;margin:0;padding-top:20px;-webkit-touch-callout:none;-webkit-user-select:none;user-select:none;}
#board{border:4px solid #555;background:#bbb;margin:0 auto;display:inline-block;padding:5px;}.row{display:flex;}
.cell{width:34px;height:34px;background:#ccc;border:2px solid;border-color:#fff #999 #999 #fff;box-sizing:border-box;text-align:center;line-height:30px;font-weight:bold;font-size:18px;}
.cell.revealed{background:#ddd;border:1px solid #999;line-height:32px;}.cell.mine{background:#f44336;}.cell.flagged{background:#ffeb3b;}
.c1{color:blue;}.c2{color:green;}.c3{color:red;}.c4{color:purple;}button{margin:20px 5px;padding:8px 20px;background:#4caf50;color:#fff;border:none;border-radius:3px;font-size:14px;cursor:pointer;}
</style></head><body><h1>Minesweeper</h1><div style="margin-bottom:10px;font-size:16px;">⏱️ <span id="timer">0</span> 秒</div><div id="board"></div><br>
<button onclick="initBoard()">重新开始</button>
<p style="font-size:12px;color:#666;margin-top:20px;">💡 操作提示：手机端长按方块插旗，轻触挖开；电脑端右键插旗。</p>
<script>
const ROWS=9,COLS=9,MINES=10;let board=[],gameOver=false,gameStarted=false,time=0,timerInterval=null;
function startGame(){if(!gameStarted){gameStarted=true;timerInterval=setInterval(()=>{time++;document.getElementById('timer').innerText=time;},1000);}}
function initBoard(){gameOver=false;gameStarted=false;time=0;clearInterval(timerInterval);document.getElementById('timer').innerText='0';const bDiv=document.getElementById('board');bDiv.innerHTML='';board=[];
for(let r=0;r<ROWS;r++){let rDiv=document.createElement('div');rDiv.className='row';board[r]=[];for(let c=0;c<COLS;c++){let cDiv=document.createElement('div');cDiv.className='cell';
cDiv.addEventListener('click',(e)=>{if(board[r][c].isFlagged||gameOver)return;startGame();revealCell(r,c);});
cDiv.addEventListener('contextmenu',(e)=>{e.preventDefault();flagCell(r,c);});
let touchTimer=null;cDiv.addEventListener('touchstart',(e)=>{e.preventDefault();touchTimer=setTimeout(()=>{flagCell(r,c);touchTimer=null;},400);},{passive:false});
cDiv.addEventListener('touchend',(e)=>{if(touchTimer){clearTimeout(touchTimer);touchTimer=null;if(!board[r][c].isFlagged&&!gameOver){startGame();revealCell(r,c);}}},{passive:false});
rDiv.appendChild(cDiv);board[r][c]={isMine:false,isRevealed:false,isFlagged:false,count:0,element:cDiv};}bDiv.appendChild(rDiv);}
let m=0;while(m<MINES){let r=Math.floor(Math.random()*ROWS),c=Math.floor(Math.random()*COLS);if(!board[r][c].isMine){board[r][c].isMine=true;m++;}}
for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++){if(board[r][c].isMine)continue;let count=0;for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++)if(board[r+dr]&&board[r+dr][c+dc]&&board[r+dr][c+dc].isMine)count++;board[r][c].count=count;}}
function revealCell(r,c){if(gameOver||board[r][c].isRevealed||board[r][c].isFlagged)return;board[r][c].isRevealed=true;let el=board[r][c].element;el.classList.add('revealed');if(board[r][c].isMine){el.classList.add('mine');el.innerText='💣';gameOver=true;clearInterval(timerInterval);setTimeout(()=>alert('💥 踩雷了!'),100);return;}
if(board[r][c].count>0){el.innerText=board[r][c].count;el.classList.add('c'+board[r][c].count);}else{for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++)if(board[r+dr]&&board[r+dr][c+dc])revealCell(r+dr,c+dc);}checkWin();}
function flagCell(r,c){if(gameOver||board[r][c].isRevealed)return;let cell=board[r][c];cell.isFlagged=!cell.isFlagged;cell.element.classList.toggle('flagged',cell.isFlagged);cell.element.innerText=cell.isFlagged?'🚩':'';}
function checkWin(){let w=true;for(let r=0;r<ROWS;r++)for(let c=0;c<COLS;c++)if(!board[r][c].isMine&&!board[r][c].isRevealed)w=false;if(w){gameOver=true;clearInterval(timerInterval);alert('🏆 赢了！');}}initBoard();
</script></body></html>
EOF

# 3. 复制启动脚本
COPY entrypoint.sh /entrypoint.sh

# 4. 强行放开脚本执行权限并转换换行符
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 7860
ENV PORT=7860

CMD ["/entrypoint.sh"]
