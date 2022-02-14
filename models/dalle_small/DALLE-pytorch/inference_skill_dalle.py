from PIL import Image
from torchvision import transforms as T
from torchvision.transforms.functional import to_pil_image
from dalle_pytorch import VQGanVAE, DALLE
from dalle_pytorch.tokenizer import tokenizer
import torch

import argparse
import json
from pathlib import Path
from dalle_pytorch.skill_loader import SkillTextImageDataset
from tqdm import tqdm

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dalle_path', default='./DALLE_CC_object.pt')
    parser.add_argument('--dataset_dir', default='/playpen3/home/jmincho/workspace/datasets/PaintSkills')
    parser.add_argument('--text_file', default='object_val.json')
    parser.add_argument('--skill_name', default='object')
    # parser.add_argument('--from_scratch', action='store_true')
    parser.add_argument('--split', type=str, default='val')
    parser.add_argument('--image_dump_dir', default='/playpen3/home/jmincho/workspace/datasets/PaintSkills/DALLE_inference')
    parser.add_argument('--batch_size', type=int, default=20)
    parser.add_argument('--text_seq_len', default=128, type=int, help='Text sequence length')
    parser.add_argument('--random_resize_crop_lower_ratio', dest='resize_ratio', type=float, default=0.75,
                        help='Random resized crop lower ratio')
    parser.add_argument('--truncate_captions', dest='truncate_captions', action='store_true',
                        help='Captions passed in which exceed the max token length will be truncated if this is set.')

    args = parser.parse_args()
    print(args)

    dalle_path = args.dalle_path
    load_obj = torch.load(dalle_path)
    dalle_params, vae_params, weights = load_obj.pop('hparams'), load_obj.pop('vae_params'), load_obj.pop('weights')
    dalle_params.pop('vae', None)  # cleanup later

    vae = VQGanVAE('./vqgan.1024.model.ckpt', './vqgan.1024.config.yml')

    print(dalle_params)

    dalle = DALLE(vae=vae, **dalle_params).to('cuda')
    dalle.load_state_dict(weights)
    dalle.eval()

    image_dir = str(Path(args.dataset_dir) / args.skill_name / 'images')
    text_data_file = str(Path(args.dataset_dir) / args.skill_name / 'scenes' / args.text_file)
    TEXT_SEQ_LEN = args.text_seq_len
    is_shuffle = False

    dataset = SkillTextImageDataset(
        skill_name=args.skill_name,
        split=args.split,
        image_dir=image_dir,
        text_data_file=text_data_file,
        text_len=TEXT_SEQ_LEN,
        resize_ratio=args.resize_ratio,
        truncate_captions=args.truncate_captions,
        tokenizer=tokenizer,
        shuffle=is_shuffle,
        load_image=False
    )

    loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        drop_last=False,
        collate_fn=dataset.text_collate_fn,
        num_workers=4,
        )

    if 'scratch' in dalle_path:
        run_name = 'scratch'
        # output_dir = Path(args.image_dump_dir).joinpath(f'{args.skill_name}_scratch_{args.split}')
    elif 'CC' in dalle_path:
        # output_dir = Path(args.image_dump_dir).joinpath(f'{args.skill_name}_CC_{args.split}')
        run_name = 'CC'
    elif 'dalle_checkpoint' in dalle_path:
        run_name = 'CCzero'
        # output_dir = Path(args.image_dump_dir).joinpath(f'{args.skill_name}_CCzero_{args.split}')

    if 'auxLR2' in dalle_path:
        run_name += '_auxLR2'
    elif 'auxLR' in dalle_path:
        run_name += '_auxLR'

    if 'overall' in dalle_path:
        run_name = 'overall_' + run_name

    output_dir = Path(args.image_dump_dir).joinpath(f'{args.skill_name}_{run_name}_{args.split}')

    if not output_dir.is_dir():
        output_dir.mkdir(parents=True)
    print('Dump images in ', output_dir)

    to_pil_image = T.ToPILImage()

    desc = f'{args.dalle_path}-{args.skill_name}-{args.split}'

    for batch in tqdm(loader, desc=desc):
        text_tokens = batch['tokenized_text']
        text_tokens = text_tokens.to('cuda')
        out_img = dalle.generate_images(
            text=text_tokens,
            filter_thres=0.9
        )

        text_ids = batch['id']

        out_img = out_img.cpu().detach()
        for i, img in enumerate(out_img):
            out_fname =  output_dir.joinpath(f'{text_ids[i]}.png')
            img = to_pil_image(img)
            img.save(out_fname)