package com.example.childmonitor;

import android.app.ActivityManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.view.KeyEvent;
import android.os.Build;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

public class QuizActivity extends AppCompatActivity {

    private TextView tvStage, tvProgress, tvQuestion;
    private EditText etAnswer;
    private Button btnSubmit;
    private ProgressBar progressBar;

    private int currentQuestionIndex = 1;
    private final int totalQuestions = 50;
    private String currentAnswer = "";
    private Random random = new Random();

    // Question lists for stage 2 and 3
    private List<QuestionItem> stage2Questions = new ArrayList<>();
    private List<QuestionItem> stage3Questions = new ArrayList<>();

    private static class QuestionItem {
        String question;
        String answer;
        QuestionItem(String q, String a) { this.question = q; this.answer = a; }
    }

    private void initQuestionBanks() {
        // Stage 2: Religion (Expanded)
        stage2Questions.add(new QuestionItem("Mencuri barang orang lain termasuk perbuatan...?", "dosa"));
        stage2Questions.add(new QuestionItem("Berbohong kepada guru dan teman adalah perbuatan...?", "dosa"));
        stage2Questions.add(new QuestionItem("Meninggalkan shalat 5 waktu bagi Muslim hukumnya...?", "dosa"));
        stage2Questions.add(new QuestionItem("Menghargai teman yang berbeda agama adalah sikap yang...?", "baik"));
        stage2Questions.add(new QuestionItem("Melawan perintah baik dari orang tua disebut anak...?", "durhaka"));
        stage2Questions.add(new QuestionItem("Iri dan dengki terhadap kesuksesan orang lain adalah penyakit...?", "hati"));
        stage2Questions.add(new QuestionItem("Berkata kasar dan kotor termasuk dosa...?", "lisan"));
        stage2Questions.add(new QuestionItem("Sengaja merusak barang milik sekolah adalah perbuatan...?", "buruk"));
        stage2Questions.add(new QuestionItem("Menolong orang yang kesusahan akan mendapatkan...?", "pahala"));
        stage2Questions.add(new QuestionItem("Membuang sampah sembarangan tidak menjaga kebersihan, padahal kebersihan sebagian dari...?", "iman"));
        stage2Questions.add(new QuestionItem("Mengambil uang kembalian belanja tanpa izin orang tua adalah...?", "mencuri"));
        stage2Questions.add(new QuestionItem("Suka memamerkan kebaikan (Riya) termasuk dosa...?", "kecil"));
        stage2Questions.add(new QuestionItem("Mendengarkan nasihat baik adalah ciri anak yang...?", "sholeh"));
        stage2Questions.add(new QuestionItem("Sombong dan merasa lebih baik dari orang lain adalah sifat...?", "iblis"));
        stage2Questions.add(new QuestionItem("Berdoa sebelum makan dan belajar adalah tanda kita... pada Tuhan.", "bersyukur"));
        stage2Questions.add(new QuestionItem("Berkata bohong demi keuntungan diri sendiri adalah dosa...?", "besar"));
        stage2Questions.add(new QuestionItem("Mengejek teman fisik atau nama orang tua adalah perbuatan...?", "tercela"));
        stage2Questions.add(new QuestionItem("Membantu teman yang jatuh adalah perbuatan...?", "mulia"));
        stage2Questions.add(new QuestionItem("Menutup aurat bagi muslimah hukumnya...?", "wajib"));
        stage2Questions.add(new QuestionItem("Sabar saat menghadapi ujian adalah sifat...?", "terpuji"));

        // Stage 3: Family (Expanded)
        stage3Questions.add(new QuestionItem("Menghormati orang tua adalah kewajiban setiap...?", "anak"));
        stage3Questions.add(new QuestionItem("Membantu ibu merapikan tempat tidur adalah perbuatan...?", "baik"));
        stage3Questions.add(new QuestionItem("Berkata 'Ah' atau membentak orang tua termasuk dosa...?", "besar"));
        stage3Questions.add(new QuestionItem("Menyayangi adik dan menghormati kakak menciptakan suasana...?", "damai"));
        stage3Questions.add(new QuestionItem("Pulang sekolah langsung rumah tanpa kabar membuat orang tua...?", "khawatir"));
        stage3Questions.add(new QuestionItem("Mendoakan kedua orang tua setiap hari adalah tanda anak...?", "bakti"));
        stage3Questions.add(new QuestionItem("Mencium tangan orang tua saat pergi dan pulang adalah bentuk...?", "hormat"));
        stage3Questions.add(new QuestionItem("Membantu ayah mencuci motor atau menyiram tanaman adalah contoh...?", "bakti"));
        stage3Questions.add(new QuestionItem("Jujur saat meminta uang jajan adalah ciri anak yang...?", "amanah"));
        stage3Questions.add(new QuestionItem("Menjaga nama baik keluarga di luar rumah adalah tugas...?", "semua"));
        stage3Questions.add(new QuestionItem("Saling memaafkan jika ada salah antar anggota keluarga itu...?", "penting"));
        stage3Questions.add(new QuestionItem("Makan bersama keluarga tanpa main HP meningkatkan...?", "keakraban"));
        stage3Questions.add(new QuestionItem("Belajar dengan tekun adalah cara membanggakan...?", "orang tua"));
        stage3Questions.add(new QuestionItem("Boros menggunakan listrik dan air di rumah tidak menghargai... orang tua.", "kerja keras"));
        stage3Questions.add(new QuestionItem("Surgamu ada di bawah telapak kaki...?", "ibu"));
        stage3Questions.add(new QuestionItem("Izin saat meminjam barang milik kakak atau adik adalah sikap...?", "sopan"));
        stage3Questions.add(new QuestionItem("Berbagi makanan dengan saudara di rumah menunjukkan rasa...?", "sayang"));
        stage3Questions.add(new QuestionItem("Menjaga rahasia keluarga adalah tanda anak yang...?", "setia"));
        stage3Questions.add(new QuestionItem("Mendengarkan saat orang tua bicara adalah bentuk...?", "hargai"));
        stage3Questions.add(new QuestionItem("Merapikan mainan setelah digunakan membantu meringankan tugas...?", "ibu"));

        Collections.shuffle(stage2Questions);
        Collections.shuffle(stage3Questions);
    }

    private BroadcastReceiver stopReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("STOP_QUIZ".equals(intent.getAction())) {
                try {
                    stopLockTask();
                } catch (Exception e) {}
                finish();
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // Lockdown flags
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD |
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED |
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON |
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        
        setContentView(R.layout.activity_quiz);

        tvStage = findViewById(R.id.tv_quiz_stage);
        tvProgress = findViewById(R.id.tv_quiz_progress);
        tvQuestion = findViewById(R.id.tv_question);
        etAnswer = findViewById(R.id.et_answer);
        btnSubmit = findViewById(R.id.btn_submit);
        progressBar = findViewById(R.id.pb_quiz);

        btnSubmit.setOnClickListener(v -> checkAnswer());

        etAnswer.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                checkAnswer();
                return true;
            }
            return false;
        });

        initQuestionBanks();
        generateQuestion();
        
        registerReceiver(stopReceiver, new IntentFilter("STOP_QUIZ"));
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        unregisterReceiver(stopReceiver);
    }

    private void generateQuestion() {
        tvProgress.setText("Soal " + currentQuestionIndex + " dari " + totalQuestions);
        progressBar.setProgress(currentQuestionIndex);

        if (currentQuestionIndex <= 20) {
            // Stage 1: Math
            tvStage.setText("TAHAP 1: MATEMATIKA");
            int a = random.nextInt(10 + currentQuestionIndex);
            int b = random.nextInt(10 + currentQuestionIndex);
            int op = random.nextInt(3); // 0: +, 1: -, 2: *

            if (op == 0) {
                tvQuestion.setText("Berapakah " + a + " + " + b + " ?");
                currentAnswer = String.valueOf(a + b);
            } else if (op == 1) {
                int max = Math.max(a, b);
                int min = Math.min(a, b);
                tvQuestion.setText("Berapakah " + max + " - " + min + " ?");
                currentAnswer = String.valueOf(max - min);
            } else {
                tvQuestion.setText("Berapakah " + a + " x " + b + " ?");
                currentAnswer = String.valueOf(a * b);
            }
        } else if (currentQuestionIndex <= 35) {
            // Stage 2: Religion
            tvStage.setText("TAHAP 2: AGAMA & DOSA");
            int idx = (currentQuestionIndex - 21) % stage2Questions.size();
            tvQuestion.setText(stage2Questions.get(idx).question);
            currentAnswer = stage2Questions.get(idx).answer;
        } else {
            // Stage 3: Family
            tvStage.setText("TAHAP 3: KELUARGA & ETIKA");
            int idx = (currentQuestionIndex - 36) % stage3Questions.size();
            tvQuestion.setText(stage3Questions.get(idx).question);
            currentAnswer = stage3Questions.get(idx).answer;
        }
        etAnswer.setText("");
    }

    private void checkAnswer() {
        String userSelection = etAnswer.getText().toString().trim().toLowerCase();
        if (userSelection.equals(currentAnswer.toLowerCase())) {
            currentQuestionIndex++;
            if (currentQuestionIndex > totalQuestions) {
                Toast.makeText(this, "KUIS SELESAI!", Toast.LENGTH_LONG).show();
                try {
                    stopLockTask();
                } catch (Exception e) {}
                finish();
            } else {
                generateQuestion();
            }
        } else {
            Toast.makeText(this, "Jawaban salah! Coba lagi.", Toast.LENGTH_SHORT).show();
        }
    }

    // LOCKDOWN MECHANISMS

    @Override
    protected void onResume() {
        super.onResume();
        checkLockState();
        hideSystemUI();
    }

    private void checkLockState() {
        ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (am != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (am.getLockTaskModeState() == ActivityManager.LOCK_TASK_MODE_NONE) {
                try {
                    startLockTask();
                } catch (Exception e) {}
            }
        } else {
            try {
                startLockTask();
            } catch (Exception e) {}
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            checkLockState();
            hideSystemUI();
        }
    }

    private void hideSystemUI() {
        View decorView = getWindow().getDecorView();
        decorView.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_FULLSCREEN);
    }

    @Override
    public void onBackPressed() {
        // Do nothing to block back button
    }

    private void bringToFront() {
        ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        if (am != null) {
            try {
                am.moveTaskToFront(getTaskId(), ActivityManager.MOVE_TASK_WITH_HOME);
            } catch (Exception e) {
                // Ignore if failed
            }
        }
    }

    @Override
    protected void onUserLeaveHint() {
        // When Home key is pressed, bring it back
        bringToFront();
        super.onUserLeaveHint();
    }

    @Override
    protected void onPause() {
        super.onPause();
        // Do NOT call startActivity here to avoid recursion crash
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_HOME || keyCode == KeyEvent.KEYCODE_APP_SWITCH 
            || keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN) {
            return true; 
        }
        return super.onKeyDown(keyCode, event);
    }
}
