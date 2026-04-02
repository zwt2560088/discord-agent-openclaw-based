#!/usr/bin/env python3
"""
🚀 真实 LoRA 微调脚本
使用 Llama-2-7B 模型或其他开源模型进行真实微调

使用方式：
  python lora_real_finetuning.py --model meta-llama/Llama-2-7b-hf --epochs 3 --r 8

参数说明：
  --model: 模型名称 (默认: meta-llama/Llama-2-7b-hf)
  --epochs: 训练轮数 (默认: 3)
  --r: LoRA 秩数 (默认: 8)
  --batch-size: 批大小 (默认: 8)
  --lr: 学习率 (默认: 1e-4)
"""

import argparse
import json
import logging
import sys
import torch
from pathlib import Path
from peft import LoraConfig, get_peft_model
from transformers import AutoTokenizer, AutoModelForCausalLM

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(title):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}🎯 {title}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.ENDC}\n")


def print_success(msg):
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")


def print_info(msg):
    print(f"{Colors.OKCYAN}ℹ️  {msg}{Colors.ENDC}")


def print_warning(msg):
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(description="LoRA 真实微调脚本")
    parser.add_argument("--model", type=str, default="meta-llama/Llama-2-7b-hf",
                        help="HuggingFace 模型名称")
    parser.add_argument("--epochs", type=int, default=3, help="训练轮数")
    parser.add_argument("--r", type=int, default=8, help="LoRA 秩数")
    parser.add_argument("--batch-size", type=int, default=8, help="批大小")
    parser.add_argument("--lr", type=float, default=1e-4, help="学习率")
    parser.add_argument("--output-dir", type=str, default="./lora_adapters",
                        help="输出目录")

    args = parser.parse_args()

    print_header("LoRA 真实微调启动")

    # 检查 GPU
    print_info("【步骤 1】检查硬件...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print_success(f"设备: {device}")

    if device == "cpu":
        print_warning("未检测到 GPU，使用 CPU 训练会很慢（推荐 GPU）")
    else:
        print_success(f"GPU: {torch.cuda.get_device_name(0)}")
        print_success(f"显存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # 加载训练数据
    print_info("【步骤 2】加载训练数据...")

    try:
        with open("train_data.json", "r", encoding="utf-8") as f:
            dataset = json.load(f)
        samples = dataset["samples"]
        print_success(f"加载样本数: {len(samples)}")
    except Exception as e:
        print(f"{Colors.FAIL}❌ 加载训练数据失败: {e}{Colors.ENDC}")
        return 1

    # 加载模型和分词器
    print_info("【步骤 3】加载模型（首次会很慢）...")

    try:
        print(f"  模型: {args.model}")
        print(f"  数据类型: float16 (混合精度)")

        tokenizer = AutoTokenizer.from_pretrained(args.model)
        model = AutoModelForCausalLM.from_pretrained(
            args.model,
            torch_dtype=torch.float16,
            device_map="auto"
        )

        print_success(f"模型加载完成")

        # 统计参数
        total_params = sum(p.numel() for p in model.parameters())
        print_success(f"模型参数: {total_params / 1e9:.1f}B")

    except Exception as e:
        print(f"{Colors.FAIL}❌ 加载模型失败: {e}{Colors.ENDC}")
        print_info("建议:")
        print("  1. 确保有网络连接")
        print("  2. 首次运行会下载 ~13GB 的模型文件")
        print("  3. 可以使用其他模型，如 Qwen、Baichuan 等")
        return 1

    # 配置 LoRA
    print_info("【步骤 4】配置 LoRA...")

    lora_config = LoraConfig(
        r=args.r,
        lora_alpha=args.r * 2,  # 通常设置为 2*r
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )

    print_success(f"秩数 (r): {args.r}")
    print_success(f"Alpha: {args.r * 2}")
    print_success(f"目标模块: q_proj, v_proj")

    # 应用 LoRA
    print_info("【步骤 5】应用 LoRA...")

    model = get_peft_model(model, lora_config)

    trainable_params = model.get_nb_trainable_parameters()
    all_params = model.get_nb_parameters()

    print_success(f"可训练参数: {trainable_params / 1e6:.2f}M")
    print_success(f"总参数数: {all_params / 1e6:.2f}M")
    print_success(f"可训练比例: {100 * trainable_params / all_params:.2f}%")

    # 训练配置
    print_info("【步骤 6】训练配置...")

    print_success(f"学习率: {args.lr}")
    print_success(f"批大小: {args.batch_size}")
    print_success(f"训练轮数: {args.epochs}")
    print_success(f"优化器: AdamW")

    # 准备训练
    print_info("【步骤 7】准备训练数据...")

    # 将样本转换为文本
    train_texts = []
    for sample in samples:
        text = f"{sample['user_input']} [SEP] {sample['expected_output']}"
        train_texts.append(text)

    print_success(f"准备了 {len(train_texts)} 个训练文本")

    # 显示训练信息
    print_header("训练开始")

    print(f"{Colors.BOLD}配置摘要:{Colors.ENDC}")
    print(f"  模型: {args.model}")
    print(f"  LoRA r: {args.r}")
    print(f"  学习率: {args.lr}")
    print(f"  批大小: {args.batch_size}")
    print(f"  训练轮数: {args.epochs}")
    print(f"  设备: {device}")
    print(f"  输出目录: {args.output_dir}")

    # 简化的训练循环演示
    print(f"\n{Colors.BOLD}训练进度:{Colors.ENDC}\n")

    from torch.optim import AdamW

    optimizer = AdamW(model.parameters(), lr=args.lr)

    total_loss = 0
    num_batches = 0

    for epoch in range(args.epochs):
        print(f"Epoch {epoch + 1}/{args.epochs}")

        # 模拟训练批次
        for batch_idx in range(0, len(train_texts), args.batch_size):
            batch_texts = train_texts[batch_idx:batch_idx + args.batch_size]

            # Tokenize
            try:
                inputs = tokenizer(
                    batch_texts,
                    max_length=512,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt"
                )

                input_ids = inputs["input_ids"].to(device)

                # 前向传播
                outputs = model(input_ids=input_ids, labels=input_ids)
                loss = outputs.loss

                # 反向传播
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

                total_loss += loss.item()
                num_batches += 1

                avg_loss = total_loss / num_batches
                print(f"  Batch {batch_idx // args.batch_size + 1}: loss={avg_loss:.4f}")

            except RuntimeError as e:
                if "out of memory" in str(e):
                    print_warning(f"显存不足，建议：")
                    print_warning(f"  1. 降低 batch_size")
                    print_warning(f"  2. 使用量化 (load_in_4bit=True)")
                    print_warning(f"  3. 启用梯度检查点 (gradient_checkpointing_enable())")
                    return 1
                else:
                    raise

        print()

    # 保存模型
    print_info("【步骤 8】保存适配器...")

    output_path = Path(args.output_dir) / "order_v1.0"
    output_path.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    print_success(f"适配器已保存到: {output_path}")

    # 总结
    print_header("微调完成")

    print(f"{Colors.BOLD}结果统计:{Colors.ENDC}")
    print(f"  总损失: {total_loss:.4f}")
    print(f"  平均损失: {total_loss / num_batches:.4f}")
    print(f"  处理的批次: {num_batches}")
    print(f"  适配器大小: ~8MB")

    print(f"\n{Colors.BOLD}下一步:{Colors.ENDC}")
    print(f"  1. 在 Discord 机器人中加载适配器")
    print(f"  2. 进行 A/B 测试")
    print(f"  3. 根据反馈持续优化")

    print_success("微调流程完成！")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}⚠️  中断退出{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ 发生错误: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

